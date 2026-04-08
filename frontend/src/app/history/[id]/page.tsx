import Link from "next/link";
import { notFound } from "next/navigation";

import { AppShell } from "@/components/layout/AppShell";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { safeGetJob } from "@/lib/api";
import type { JobRecord } from "@/lib/types";

export const dynamic = "force-dynamic";

const STATUS_TONE: Record<string, BadgeTone> = {
  closed: "emerald",
  in_progress: "amber",
  open: "rose",
};

function formatDate(iso?: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default async function JobDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const job = await safeGetJob(params.id);
  if (!job) {
    notFound();
  }
  const record: JobRecord = job;

  return (
    <AppShell subtitle="Job detail">
      <header className="mb-7">
        <Link
          href="/history"
          className="text-[11.5px] uppercase tracking-[0.14em] text-ink-400 hover:text-cyan-300"
        >
          ← Back to history
        </Link>
        <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="pill mb-3">Discrepancy</div>
            <h1 className="text-[26px] font-semibold leading-tight tracking-[-0.01em] text-ink-100 md:text-[32px]">
              {record.discrepancy}
            </h1>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px] text-ink-400">
              <span className="mono-meta">{record.id}</span>
              <span>·</span>
              <span>{record.aircraft}</span>
              {record.tail_number && (
                <>
                  <span>·</span>
                  <span className="mono-meta">{record.tail_number}</span>
                </>
              )}
              {record.ata && (
                <>
                  <span>·</span>
                  <span className="font-mono">ATA {record.ata}</span>
                </>
              )}
              {record.work_order && (
                <>
                  <span>·</span>
                  <span className="mono-meta">WO {record.work_order}</span>
                </>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <Badge tone={STATUS_TONE[record.status] ?? "neutral"} dot>
              {record.status}
            </Badge>
            <div className="mono-meta text-[11px] text-ink-400">
              {formatDate(record.occurred_on)}
            </div>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          {record.symptoms && (
            <Card title="Symptoms">
              <p className="whitespace-pre-line text-[13px] leading-relaxed text-ink-200">
                {record.symptoms}
              </p>
            </Card>
          )}
          {record.actions_taken && (
            <Card title="Actions taken">
              <p className="whitespace-pre-line text-[13px] leading-relaxed text-ink-200">
                {record.actions_taken}
              </p>
            </Card>
          )}
          {record.corrective_action && (
            <Card
              title="Corrective action"
              subtitle="What returned the aircraft to service"
              variant="accent"
            >
              <p className="whitespace-pre-line text-[13.5px] leading-relaxed text-ink-100">
                {record.corrective_action}
              </p>
            </Card>
          )}
          {record.technician_notes && (
            <Card title="Technician notes">
              <p className="whitespace-pre-line text-[13px] leading-relaxed text-ink-200">
                {record.technician_notes}
              </p>
            </Card>
          )}
        </div>

        <div className="space-y-5">
          <Card title="Indexing">
            <ul className="space-y-2 text-[12px]">
              <Row k="indexed" v={record.indexed ? "yes" : "no"} />
              <Row k="chunks" v={String(record.chunk_count)} />
              <Row k="source_family" v="HISTORY" />
              <Row k="document_id" v={record.document_id} mono />
            </ul>
            <Link
              href={`/library/${record.document_id}`}
              className="mt-3 inline-block text-[11.5px] uppercase tracking-[0.12em] text-cyan-300 hover:text-cyan-200"
            >
              Open document in library →
            </Link>
          </Card>
          {record.parts_replaced.length > 0 && (
            <Card title="Parts replaced">
              <ul className="space-y-1 text-[12.5px]">
                {record.parts_replaced.map((p) => (
                  <li
                    key={p}
                    className="mono-meta rounded-md border border-white/[0.06] bg-gunmetal-900/60 px-2 py-1"
                  >
                    {p}
                  </li>
                ))}
              </ul>
            </Card>
          )}
          <Card title="Crew">
            <ul className="space-y-2 text-[12px]">
              <Row k="technician" v={record.technician ?? "—"} />
              <Row k="work_order" v={record.work_order ?? "—"} />
              <Row k="created_at" v={formatDate(record.created_at)} />
            </ul>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}

function Row({
  k,
  v,
  mono = false,
}: {
  k: string;
  v: string;
  mono?: boolean;
}) {
  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-white/[0.06] bg-gunmetal-900/60 px-3 py-2">
      <span className="label-eyebrow">{k}</span>
      <span
        className={`truncate ${mono ? "font-mono text-[11px] text-cyan-200" : "text-[12px] text-ink-100"}`}
      >
        {v}
      </span>
    </li>
  );
}
