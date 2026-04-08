import Link from "next/link";

import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import type { PriorSimilarJob } from "@/lib/types";

const STATUS_TONE: Record<string, BadgeTone> = {
  closed: "emerald",
  in_progress: "amber",
  open: "rose",
};

function formatDate(iso?: string | null): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

export function PriorSimilarJobsPanel({
  jobs,
}: {
  jobs: PriorSimilarJob[] | undefined | null;
}) {
  const items = jobs ?? [];

  return (
    <Card
      variant="accent"
      title="Seen before"
      subtitle="Structured discrepancy history from your shop"
      action={
        items.length > 0 ? (
          <span className="pill-cyan">{items.length} match</span>
        ) : (
          <Link
            href="/history"
            className="label-eyebrow text-cyan-300 hover:text-cyan-200"
          >
            Log a job →
          </Link>
        )
      }
    >
      {items.length === 0 ? (
        <EmptyState
          glyph="◇"
          title="No prior fix on record"
          body="When a similar discrepancy has been logged in /history, the top matches will show here with the corrective action that worked."
        />
      ) : (
        <ul className="space-y-3">
          {items.map((j) => {
            const dateLabel = formatDate(j.occurred_on);
            return (
              <li
                key={j.id}
                className="rounded-xl border border-cyan-400/20 bg-cyan-500/[0.04] p-4 transition hover:border-cyan-400/40"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tone={STATUS_TONE[j.status] ?? "neutral"} dot>
                        {j.status}
                      </Badge>
                      <Badge tone="neutral">HISTORY</Badge>
                      {j.ata && (
                        <span className="mono-meta">ATA {j.ata}</span>
                      )}
                      {dateLabel && (
                        <span className="mono-meta">{dateLabel}</span>
                      )}
                    </div>
                    <Link
                      href={`/history/${j.id}`}
                      className="mt-2 block text-[13.5px] font-semibold text-ink-100 hover:text-cyan-200"
                    >
                      {j.discrepancy}
                    </Link>
                    <div className="mt-1 flex flex-wrap gap-x-3 text-[11px] uppercase tracking-[0.1em] text-ink-400">
                      <span>{j.aircraft}</span>
                      {j.tail_number && (
                        <span className="mono-meta normal-case tracking-normal">
                          {j.tail_number}
                        </span>
                      )}
                      {j.technician && (
                        <span>tech · {j.technician}</span>
                      )}
                    </div>
                    {j.corrective_action && (
                      <div className="mt-3 rounded-md border border-emerald-400/30 bg-emerald-500/[0.05] p-3 text-[12px] leading-relaxed text-emerald-100">
                        <div className="label-eyebrow mb-1 text-emerald-300">
                          Corrective action that worked
                        </div>
                        {j.corrective_action}
                      </div>
                    )}
                    {j.snippet && !j.corrective_action && (
                      <blockquote className="mt-2 border-l-2 border-cyan-400/40 pl-3 text-[12px] italic leading-relaxed text-ink-300">
                        {j.snippet}
                      </blockquote>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <div className="font-mono text-[12px] text-cyan-300">
                      {j.score.toFixed(2)}
                    </div>
                    <div className="label-eyebrow">match</div>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
