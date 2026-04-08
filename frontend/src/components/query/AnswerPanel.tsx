import { Card } from "@/components/ui/Card";
import { ConfidenceBadge } from "@/components/query/ConfidenceBadge";
import type { QueryResponse, SourceFamily } from "@/lib/types";

const FAMILY_TONE: Record<SourceFamily | "default", string> = {
  FIM: "border-cyan-400/40 bg-cyan-500/[0.05]",
  WDM: "border-violet-400/40 bg-violet-500/[0.05]",
  AMM: "border-emerald-400/40 bg-emerald-500/[0.04]",
  IPC: "border-amber-400/40 bg-amber-500/[0.04]",
  SB: "border-rose-400/40 bg-rose-500/[0.04]",
  HISTORY: "border-blue-400/40 bg-blue-500/[0.04]",
  BROWSER: "border-fuchsia-400/40 bg-fuchsia-500/[0.05]",
  EXTERNAL: "border-amber-300/40 bg-amber-400/[0.05]",
  OTHER: "border-white/[0.08] bg-white/[0.03]",
  default: "border-white/[0.08] bg-gunmetal-900/50",
};

const FAMILY_LABEL_TONE: Record<SourceFamily | "default", string> = {
  FIM: "text-cyan-300",
  WDM: "text-violet-300",
  AMM: "text-emerald-300",
  IPC: "text-amber-300",
  SB: "text-rose-300",
  HISTORY: "text-blue-300",
  BROWSER: "text-fuchsia-300",
  EXTERNAL: "text-amber-200",
  OTHER: "text-ink-300",
  default: "text-cyan-300",
};

export function AnswerPanel({ response }: { response: QueryResponse }) {
  const path = response.troubleshooting_path ?? [];
  const groupedSections = response.sections.filter(
    (s) => s.heading !== "Missing likely sources",
  );
  return (
    <Card
      variant="accent"
      title="Executive answer"
      subtitle={`Synthesized from ${response.citations.length} cited chunks across ${groupedSections.filter((s) => s.family).length} source families`}
      action={<span className="pill-cyan">mission panel</span>}
    >
      <p className="whitespace-pre-line text-[14.5px] leading-[1.65] text-ink-100">
        {response.answer}
      </p>

      <div className="mt-5">
        <ConfidenceBadge report={response.confidence} />
      </div>

      {path.length > 0 && (
        <section className="mt-6 rounded-xl border border-cyan-400/30 bg-cyan-500/[0.04] p-4">
          <div className="label-eyebrow mb-2 text-cyan-300">
            Likely troubleshooting path
          </div>
          <ol className="space-y-2 text-[13px] text-ink-200">
            {path.map((step, idx) => (
              <li key={idx} className="flex items-start gap-2.5">
                <span className="mt-[2px] inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-cyan-400/40 text-[10px] font-semibold text-cyan-200">
                  {idx + 1}
                </span>
                <span className="leading-relaxed">{step}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {groupedSections.length > 0 && (
        <div className="mt-6 space-y-4">
          {groupedSections.map((section) => {
            const tone =
              FAMILY_TONE[section.family ?? "default"] ?? FAMILY_TONE.default;
            const labelTone =
              FAMILY_LABEL_TONE[section.family ?? "default"] ??
              FAMILY_LABEL_TONE.default;
            return (
              <section
                key={section.heading}
                className={`rounded-xl border p-4 ${tone}`}
              >
                <div className="mb-2 flex items-center gap-2">
                  <span className={`label-eyebrow ${labelTone}`}>
                    {section.heading}
                  </span>
                  {section.family && (
                    <span className="rounded-full border border-white/10 px-2 py-[1px] text-[10px] uppercase tracking-[0.12em] text-ink-400">
                      {section.family}
                    </span>
                  )}
                </div>
                <ul className="space-y-2 text-[13px] text-ink-200">
                  {section.bullets.map((b, idx) => (
                    <li key={idx} className="flex items-start gap-2.5">
                      <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-cyan-400" />
                      <span className="leading-relaxed">{b}</span>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      )}
    </Card>
  );
}
