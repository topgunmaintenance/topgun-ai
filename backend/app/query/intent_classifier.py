"""Query intent classifier.

Turns a free-text question into a structured ``QueryIntent`` that
downstream stages can reason about:

- ``aircraft`` — best-guess aircraft model (e.g. "Phenom 300")
- ``symptom`` — short symptom phrase if one was clearly stated
- ``component_hints`` — names of components / sub-systems mentioned
- ``system_hints`` — broader system labels (autoflight, electrical, ...)
- ``ata_hints`` — predicted ATA chapters (e.g. "22", "27")
- ``intent_kind`` — the kind of question (troubleshooting / procedure /
  parts / wiring / bulletin / history / general)
- ``family_priority`` — ordered list of source families to search,
  most important first
- ``family_weights`` — weight per family for rank fusion

The implementation is deterministic, dependency-free, and tested. The
real-LLM upgrade lives behind the same interface so the engine and
tests don't have to change.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.source_family import (
    DEFAULT_FAMILY_WEIGHTS,
    SourceFamily,
    families_in_priority_order,
)


# ---------------------------------------------------------------------------
# Knowledge tables
# ---------------------------------------------------------------------------
# Aircraft model patterns. We list common phrasings so the matcher works
# on conversational questions ("on a Phenom 300", "for the Citation XLS").
_AIRCRAFT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Phenom 300", re.compile(r"\bphenom\s*300\b", re.IGNORECASE)),
    ("Phenom 100", re.compile(r"\bphenom\s*100\b", re.IGNORECASE)),
    ("Citation XLS", re.compile(r"\bcitation\s*xls\b", re.IGNORECASE)),
    ("Citation CJ3", re.compile(r"\bcj\s*3\b|\bcitation\s*cj3\b", re.IGNORECASE)),
    ("King Air 350", re.compile(r"\bking\s*air\s*350\b", re.IGNORECASE)),
    ("King Air 200", re.compile(r"\bking\s*air\s*200\b", re.IGNORECASE)),
    ("Pilatus PC-12", re.compile(r"\bpc[- ]?12\b", re.IGNORECASE)),
    ("Gulfstream G450", re.compile(r"\bg\s*450\b", re.IGNORECASE)),
    ("Gulfstream G550", re.compile(r"\bg\s*550\b", re.IGNORECASE)),
]


# Component / system hint table. Each entry maps a regex (matched
# case-insensitively against the question) to:
#   - a component label
#   - a system label
#   - the candidate ATA chapters that component typically falls under
@dataclass(frozen=True)
class _ComponentHint:
    component: str
    system: str
    ata_chapters: tuple[str, ...]


_COMPONENT_TABLE: list[tuple[re.Pattern[str], _ComponentHint]] = [
    (
        re.compile(r"\btoga\b|\btake[- ]?off.{0,4}go.?around\b", re.IGNORECASE),
        _ComponentHint("TOGA switch", "autoflight", ("22", "27")),
    ),
    (
        re.compile(r"\bautopilot\b|\bautoflight\b|\bservo\b", re.IGNORECASE),
        _ComponentHint("Autopilot", "autoflight", ("22",)),
    ),
    (
        re.compile(r"\bflap[s]?\b", re.IGNORECASE),
        _ComponentHint("Flaps", "high-lift", ("27",)),
    ),
    (
        re.compile(r"\baileron|elevator|rudder|trim\b", re.IGNORECASE),
        _ComponentHint("Flight control surface", "flight controls", ("27",)),
    ),
    (
        re.compile(r"\bhydraulic|pump|reservoir\b", re.IGNORECASE),
        _ComponentHint("Hydraulic system", "hydraulics", ("29",)),
    ),
    (
        re.compile(r"\blanding\s*gear|mlg|nlg\b", re.IGNORECASE),
        _ComponentHint("Landing gear", "landing gear", ("32",)),
    ),
    (
        re.compile(r"\bbrake|antiskid|wheel\b", re.IGNORECASE),
        _ComponentHint("Wheels & brakes", "landing gear", ("32",)),
    ),
    (
        re.compile(r"\bavionics|fmc|fms|display unit|du\b", re.IGNORECASE),
        _ComponentHint("Avionics suite", "avionics", ("31", "34")),
    ),
    (
        re.compile(r"\belectric|relay|fuse|breaker|wire|harness|connector|pin\b", re.IGNORECASE),
        _ComponentHint("Electrical wiring", "electrical", ("24",)),
    ),
    (
        re.compile(r"\bbattery\b", re.IGNORECASE),
        _ComponentHint("Battery", "electrical power", ("24",)),
    ),
    (
        re.compile(r"\bgenerator|alternator|gcu\b", re.IGNORECASE),
        _ComponentHint("Generator", "electrical power", ("24",)),
    ),
    (
        re.compile(r"\bbleed|pneumatic|pack|pcu\b", re.IGNORECASE),
        _ComponentHint("Pneumatic / bleed", "pneumatic", ("36",)),
    ),
    (
        re.compile(r"\bpressuriz|cabin altitude\b", re.IGNORECASE),
        _ComponentHint("Pressurization", "ECS", ("21",)),
    ),
    (
        re.compile(r"\bengine|n1|n2|itt|ecu\b", re.IGNORECASE),
        _ComponentHint("Engine", "powerplant", ("71", "73", "77")),
    ),
    (
        re.compile(r"\bfuel\b", re.IGNORECASE),
        _ComponentHint("Fuel system", "fuel", ("28",)),
    ),
    (
        re.compile(r"\bignition|ignitor\b", re.IGNORECASE),
        _ComponentHint("Ignition", "powerplant", ("74",)),
    ),
    (
        re.compile(r"\bstarter\b", re.IGNORECASE),
        _ComponentHint("Starter", "powerplant", ("80",)),
    ),
    (
        re.compile(r"\bicing|anti[- ]?ice|de[- ]?ice|boot\b", re.IGNORECASE),
        _ComponentHint("Ice protection", "ice & rain", ("30",)),
    ),
    (
        re.compile(r"\boxygen\b", re.IGNORECASE),
        _ComponentHint("Oxygen system", "oxygen", ("35",)),
    ),
]


# Symptom verb table — used to recognize "X is broken / inop / failed".
_SYMPTOM_VERBS = re.compile(
    r"\b(not\s*working|inoperative|inop|fail(?:ed|ing|ure)?|fault|"
    r"intermittent|stuck|frozen|won't|will not|"
    r"low|high|fluctuat(?:e|ing|ion))\b",
    re.IGNORECASE,
)


# Intent kind classifier patterns. Order matters — first match wins.
_INTENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("wiring", re.compile(r"\bwir(e|ing)|connector|pin|harness|relay|breaker\b", re.IGNORECASE)),
    ("parts", re.compile(r"\bpart\s*number|p/?n\b|ipc|order|spare\b", re.IGNORECASE)),
    (
        "procedure",
        re.compile(
            r"\bhow do i (replace|install|remove|service|inspect|adjust|rig)|"
            r"\b(replac|instal|remov|servic|inspect|adjust|rig)(e|ing|ation|ed)\b|"
            r"\bprocedure\b|\bremoval\b|\binstallation\b|\brigging\b",
            re.IGNORECASE,
        ),
    ),
    ("bulletin", re.compile(r"\bbulletin|sb-?\d|service letter|alert\b", re.IGNORECASE)),
    (
        "history",
        re.compile(
            r"\b(work order|logbook|history|prior|previous|last time|tail [a-z]?\d)\b",
            re.IGNORECASE,
        ),
    ),
]


# ---------------------------------------------------------------------------
# QueryIntent dataclass
# ---------------------------------------------------------------------------
@dataclass
class QueryIntent:
    raw_question: str
    aircraft: str | None = None
    symptom: str | None = None
    component_hints: list[str] = field(default_factory=list)
    system_hints: list[str] = field(default_factory=list)
    ata_hints: list[str] = field(default_factory=list)
    intent_kind: str = "general"
    family_priority: list[SourceFamily] = field(default_factory=list)
    family_weights: dict[SourceFamily, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "raw_question": self.raw_question,
            "aircraft": self.aircraft,
            "symptom": self.symptom,
            "component_hints": list(self.component_hints),
            "system_hints": list(self.system_hints),
            "ata_hints": list(self.ata_hints),
            "intent_kind": self.intent_kind,
            "family_priority": list(self.family_priority),
            "family_weights": dict(self.family_weights),
        }


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------
class QueryIntentClassifier:
    """Heuristic intent classifier.

    Use ``classify(question)`` to get a ``QueryIntent``. The classifier
    is purposely deterministic so unit tests can pin behavior. A future
    LLM-backed implementation can replace this class behind the same
    interface.
    """

    def classify(self, question: str) -> QueryIntent:
        text = question or ""
        intent = QueryIntent(raw_question=text)
        intent.aircraft = self._aircraft(text)

        components, systems, atas = self._components_systems(text)
        intent.component_hints = components
        intent.system_hints = systems
        intent.ata_hints = sorted(set(atas))

        intent.symptom = self._symptom(text, components)
        intent.intent_kind = self._intent_kind(text, components)

        weights = self._family_weights(intent.intent_kind)
        intent.family_weights = weights
        intent.family_priority = families_in_priority_order(weights)
        return intent

    # ------------------------------------------------------------------
    @staticmethod
    def _aircraft(text: str) -> str | None:
        for label, pattern in _AIRCRAFT_PATTERNS:
            if pattern.search(text):
                return label
        return None

    @staticmethod
    def _components_systems(
        text: str,
    ) -> tuple[list[str], list[str], list[str]]:
        components: list[str] = []
        systems: list[str] = []
        atas: list[str] = []
        for pattern, hint in _COMPONENT_TABLE:
            if pattern.search(text):
                if hint.component not in components:
                    components.append(hint.component)
                if hint.system not in systems:
                    systems.append(hint.system)
                atas.extend(hint.ata_chapters)
        # Direct ATA mentions in the question.
        for m in re.finditer(r"\bATA\s?(\d{2})\b", text, re.IGNORECASE):
            atas.append(m.group(1))
        return components, systems, atas

    @staticmethod
    def _symptom(text: str, components: list[str]) -> str | None:
        verb = _SYMPTOM_VERBS.search(text)
        if not verb:
            return None
        # Build a short symptom phrase: prefer "<component> <verb>".
        if components:
            return f"{components[0]} {verb.group(0).lower()}"
        # Fall back to a clipped substring around the verb.
        start = max(0, verb.start() - 24)
        end = min(len(text), verb.end() + 16)
        return text[start:end].strip()

    @staticmethod
    def _intent_kind(text: str, components: list[str]) -> str:
        # If a symptom verb is present, treat as troubleshooting first.
        if _SYMPTOM_VERBS.search(text):
            return "troubleshooting"
        for kind, pattern in _INTENT_PATTERNS:
            if pattern.search(text):
                return kind
        return "general"

    @staticmethod
    def _family_weights(intent_kind: str) -> dict[SourceFamily, float]:
        """Return per-family weights skewed by intent kind.

        These weights are passed straight into the rank-fusion stage so
        the right family wins ties.
        """
        base = dict(DEFAULT_FAMILY_WEIGHTS)
        if intent_kind == "troubleshooting":
            base.update(
                {
                    "FIM": 1.60,
                    "WDM": 1.40,
                    "AMM": 1.20,
                    "IPC": 1.00,
                    "SB": 0.95,
                    "HISTORY": 0.90,
                    "BROWSER": 1.15,
                    "EXTERNAL": 0.75,
                }
            )
        elif intent_kind == "wiring":
            base.update(
                {"WDM": 1.60, "FIM": 1.20, "AMM": 1.00, "IPC": 0.95, "BROWSER": 1.10}
            )
        elif intent_kind == "parts":
            base.update(
                {"IPC": 1.50, "AMM": 1.05, "FIM": 0.90, "WDM": 0.80, "BROWSER": 1.05}
            )
        elif intent_kind == "procedure":
            base.update(
                {"AMM": 1.45, "FIM": 1.10, "IPC": 1.05, "WDM": 0.95, "BROWSER": 1.05}
            )
        elif intent_kind == "bulletin":
            base.update({"SB": 1.55, "AMM": 1.05, "HISTORY": 1.00, "BROWSER": 1.00})
        elif intent_kind == "history":
            base.update({"HISTORY": 1.55, "FIM": 1.05, "AMM": 0.95, "BROWSER": 0.95})
        return base


# Module-level convenience.
def classify_question(question: str) -> QueryIntent:
    return QueryIntentClassifier().classify(question)
