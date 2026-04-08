import Link from "next/link";
import { notFound } from "next/navigation";

import { Badge, docTypeTone, statusTone } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { AppShell } from "@/components/layout/AppShell";
import { safeGetDocument } from "@/lib/api";
import type { ChunkPreview, IngestionReport } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function DocumentDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const doc = await safeGetDocument(params.id);
  if (!doc) {
    notFound();
  }

  const ingestion: IngestionReport | null | undefined = doc.ingestion;
  const previews: ChunkPreview[] = doc.chunk_previews ?? [];
  const fields = ingestion?.extracted_fields ?? {};

  return (
    <AppShell subtitle="Document detail">
      <header className="mb-7">
        <Link
          href="/library"
          className="text-[11.5px] uppercase tracking-[0.14em] text-ink-400 hover:text-cyan-300"
        >
          ← Back to library
        </Link>
        <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={docTypeTone(doc.type)}>{doc.type}</Badge>
              <Badge tone={statusTone(doc.status)} dot>
                {doc.status}
              </Badge>
              {doc.tags.slice(0, 4).map((t) => (
                <span key={t} className="pill">
                  {t}
                </span>
              ))}
            </div>
            <h1 className="mt-3 text-[26px] font-semibold leading-tight tracking-[-0.01em] text-ink-100 md:text-[32px]">
              {doc.title}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-ink-400">
              <span className="mono-meta">{doc.id}</span>
              {doc.aircraft && <span>Aircraft: {doc.aircraft}</span>}
              {doc.source && <span>Source: {doc.source}</span>}
              {doc.uploaded_at && (
                <span>
                  Uploaded {new Date(doc.uploaded_at).toLocaleString()}
                </span>
              )}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 text-right md:grid-cols-4">
            <Stat label="Pages" value={doc.pages ?? "—"} />
            <Stat label="Size" value={doc.size_mb ? `${doc.size_mb} MB` : "—"} />
            <Stat
              label="Chunks"
              value={ingestion?.chunk_count ?? previews.length ?? "—"}
            />
            <Stat
              label="Parser"
              value={ingestion?.parser_backend ?? "demo"}
              mono
            />
          </div>
        </div>
      </header>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Summary" subtitle="What ingestion found">
            {doc.summary ? (
              <p className="text-[13px] leading-relaxed text-ink-200">
                {doc.summary}
              </p>
            ) : (
              <EmptyState
                glyph="∅"
                title="No summary yet"
                body="Re-upload the document to refresh its summary."
              />
            )}
          </Card>

          <Card
            title="Indexed chunks"
            subtitle={
              previews.length
                ? `Showing ${previews.length} of ${ingestion?.chunk_count ?? previews.length}`
                : "No indexed chunks for this document"
            }
          >
            {previews.length === 0 ? (
              <EmptyState
                glyph="❐"
                title="Nothing in the vector store yet"
                body="This document was seeded as demo data or hasn't been ingested. Upload it again from the dashboard to populate the index."
              />
            ) : (
              <ul className="divide-y divide-white/[0.06]">
                {previews.map((c) => (
                  <li key={c.id} className="py-3 first:pt-0 last:pb-0">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-[10.5px] uppercase tracking-[0.12em] text-ink-400">
                      <span className="mono-meta text-ink-300">
                        page {c.page_start}
                        {c.page_end !== c.page_start ? `–${c.page_end}` : ""} ·
                        chunk {c.position}
                      </span>
                      <div className="flex items-center gap-1.5">
                        <Badge
                          tone={c.ocr ? "amber" : "neutral"}
                          className="!text-[9px]"
                        >
                          {c.source}
                        </Badge>
                        {c.ocr && (
                          <Badge tone="amber" className="!text-[9px]">
                            OCR
                          </Badge>
                        )}
                        <span className="mono-meta text-ink-400">
                          ~{c.token_estimate} tok
                        </span>
                      </div>
                    </div>
                    <p className="mt-1.5 text-[13px] leading-relaxed text-ink-200">
                      {c.snippet}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card
            title="Ingestion report"
            subtitle="What the pipeline did, end to end"
          >
            <dl className="space-y-2 text-[12.5px]">
              <Row label="Parser backend" value={ingestion?.parser_backend ?? "—"} />
              <Row label="Pages" value={ingestion?.page_count ?? "—"} />
              <Row label="Chunks" value={ingestion?.chunk_count ?? "—"} />
              <Row
                label="Indexed"
                value={ingestion?.indexed ? "Yes" : "No"}
                tone={ingestion?.indexed ? "emerald" : "amber"}
              />
              <Row
                label="OCR applied"
                value={
                  ingestion?.ocr_applied
                    ? `Yes (${ingestion.ocr_pages.length} pages)`
                    : ingestion?.ocr_skipped_reason
                      ? `Skipped — ${ingestion.ocr_skipped_reason}`
                      : "No"
                }
                tone={ingestion?.ocr_applied ? "amber" : "neutral"}
              />
              {ingestion?.error && (
                <Row label="Error" value={ingestion.error} tone="rose" />
              )}
            </dl>
          </Card>

          <Card
            title="Extracted fields"
            subtitle="Surfaced from the parsed text"
          >
            <div className="space-y-3 text-[12.5px]">
              <FieldList label="Tail numbers" values={fields.tail_numbers} />
              <FieldList label="ATA chapters" values={fields.ata_chapters} />
              <FieldList label="Part numbers" values={fields.part_numbers} />
              <FieldList label="Dates" values={fields.dates} />
            </div>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}

function Stat({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: number | string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-left">
      <div className="label-eyebrow text-ink-400">{label}</div>
      <div
        className={`mt-1 text-[15px] font-semibold text-ink-100 ${
          mono ? "font-mono text-[13px]" : ""
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: number | string;
  tone?: "neutral" | "emerald" | "amber" | "rose";
}) {
  const toneClass =
    tone === "emerald"
      ? "text-emerald-300"
      : tone === "amber"
        ? "text-amber-300"
        : tone === "rose"
          ? "text-rose-300"
          : "text-ink-100";
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-ink-400">{label}</dt>
      <dd className={`text-right font-medium ${toneClass}`}>{value}</dd>
    </div>
  );
}

function FieldList({
  label,
  values,
}: {
  label: string;
  values: unknown;
}) {
  const arr = Array.isArray(values) ? (values as string[]) : [];
  return (
    <div>
      <div className="label-eyebrow text-ink-400">{label}</div>
      {arr.length === 0 ? (
        <div className="mt-1 text-ink-500">None detected</div>
      ) : (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {arr.slice(0, 12).map((v) => (
            <span key={v} className="pill mono-meta">
              {v}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
