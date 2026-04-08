import Link from "next/link";

import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import type { JobSummary } from "@/lib/types";

const STATUS_TONE: Record<string, BadgeTone> = {
  closed: "emerald",
  in_progress: "amber",
  open: "rose",
};

function formatDate(iso?: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

export function JobList({ jobs }: { jobs: JobSummary[] }) {
  if (jobs.length === 0) {
    return (
      <Card>
        <EmptyState
          glyph="◇"
          title="No discrepancies logged yet"
          body="Create your first job from the panel on the right. Each job is indexed into the HISTORY source family and becomes searchable from the Query Workspace."
        />
      </Card>
    );
  }

  return (
    <div className="panel-accent overflow-hidden p-0">
      <div className="grid grid-cols-12 gap-3 border-b border-white/[0.06] bg-gunmetal-900/60 px-5 py-3">
        <div className="col-span-5 label-eyebrow">Discrepancy</div>
        <div className="col-span-2 label-eyebrow">Aircraft</div>
        <div className="col-span-1 label-eyebrow">ATA</div>
        <div className="col-span-2 label-eyebrow">Technician</div>
        <div className="col-span-1 label-eyebrow">Date</div>
        <div className="col-span-1 label-eyebrow text-right">Status</div>
      </div>
      <ul className="divide-y divide-white/[0.06]">
        {jobs.map((j) => (
          <li
            key={j.id}
            className="grid grid-cols-12 items-start gap-3 px-5 py-4 text-[13px] transition hover:bg-white/[0.025]"
          >
            <div className="col-span-5 min-w-0 pr-3">
              <Link
                href={`/history/${j.id}`}
                className="block truncate font-medium text-ink-100 transition hover:text-cyan-200"
              >
                {j.discrepancy}
              </Link>
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-400">
                <span className="mono-meta">{j.id}</span>
                {j.work_order && (
                  <span className="mono-meta">WO {j.work_order}</span>
                )}
              </div>
            </div>
            <div className="col-span-2 min-w-0 truncate text-ink-200">
              <div>{j.aircraft}</div>
              {j.tail_number && (
                <div className="mono-meta text-[11px]">{j.tail_number}</div>
              )}
            </div>
            <div className="col-span-1 font-mono text-ink-300">
              {j.ata ?? "—"}
            </div>
            <div className="col-span-2 truncate text-ink-300">
              {j.technician ?? "—"}
            </div>
            <div className="col-span-1 font-mono text-[11px] text-ink-400">
              {formatDate(j.occurred_on || j.created_at)}
            </div>
            <div className="col-span-1 flex justify-end">
              <Badge tone={STATUS_TONE[j.status] ?? "neutral"} dot>
                {j.status}
              </Badge>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
