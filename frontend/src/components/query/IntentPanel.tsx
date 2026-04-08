import { Card } from "@/components/ui/Card";
import type { QueryIntentSummary } from "@/lib/types";

export function IntentPanel({
  intent,
}: {
  intent?: QueryIntentSummary | null;
}) {
  if (!intent) return null;
  return (
    <Card title="Detected intent" subtitle="What Topgun AI inferred from the question">
      <dl className="space-y-2 text-[12.5px]">
        <Row label="Intent kind" value={intent.intent_kind} mono />
        <Row label="Aircraft" value={intent.aircraft || "—"} />
        <Row label="Symptom" value={intent.symptom || "—"} />
        <ListRow label="Components" values={intent.component_hints} />
        <ListRow label="Systems" values={intent.system_hints} />
        <ListRow label="Predicted ATA" values={intent.ata_hints} />
        <ListRow label="Family priority" values={intent.family_priority} mono />
      </dl>
    </Card>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-ink-400">{label}</dt>
      <dd
        className={`text-right text-ink-100 ${mono ? "font-mono text-[11.5px]" : ""}`}
      >
        {value}
      </dd>
    </div>
  );
}

function ListRow({
  label,
  values,
  mono = false,
}: {
  label: string;
  values: string[];
  mono?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-ink-400">{label}</dt>
      <dd className="flex max-w-[60%] flex-wrap justify-end gap-1">
        {values.length === 0 ? (
          <span className="text-ink-500">—</span>
        ) : (
          values.map((v) => (
            <span
              key={v}
              className={`pill ${mono ? "mono-meta" : ""}`}
            >
              {v}
            </span>
          ))
        )}
      </dd>
    </div>
  );
}
