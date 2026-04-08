import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import type { Citation, SourceFamily } from "@/lib/types";

const FAMILY_TONE: Record<SourceFamily, BadgeTone> = {
  FIM: "cyan",
  WDM: "violet",
  AMM: "emerald",
  IPC: "amber",
  SB: "rose",
  HISTORY: "neutral",
  BROWSER: "violet",
  EXTERNAL: "amber",
  OTHER: "neutral",
};

export function CitationsPanel({ citations }: { citations: Citation[] }) {
  return (
    <Card
      title="Citations"
      subtitle="Chunk-level source evidence"
      action={
        citations.length > 0 ? (
          <span className="pill">{citations.length} sources</span>
        ) : null
      }
    >
      {citations.length === 0 ? (
        <EmptyState
          glyph="∅"
          title="No evidence retrieved"
          body="Topgun AI refuses to answer without cited sources. Upload a relevant manual, push a browser page, or connect a manual portal."
        />
      ) : (
        <ul className="space-y-3">
          {citations.map((c, idx) => {
            const family = (c.source_family || "OTHER") as SourceFamily;
            const tone = FAMILY_TONE[family];
            return (
              <li
                key={`${c.document_id}-${c.page}-${idx}`}
                className="group cursor-pointer rounded-xl border border-white/[0.06] bg-gunmetal-900/60 p-4 transition hover:border-cyan-500/30 hover:bg-gunmetal-900/80"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tone={tone}>{family}</Badge>
                      <Badge tone="neutral">{c.document_type}</Badge>
                      <span className="mono-meta">p. {c.page}</span>
                      {c.weak && (
                        <Badge tone="amber" className="!text-[9px]">
                          weak
                        </Badge>
                      )}
                      {c.ocr && (
                        <Badge tone="amber" className="!text-[9px]">
                          OCR
                        </Badge>
                      )}
                    </div>
                    <div className="mt-2 truncate text-[13px] font-medium text-ink-100">
                      {c.document_title}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10.5px] uppercase tracking-[0.1em] text-ink-400">
                      {c.document_code && (
                        <span className="mono-meta normal-case tracking-normal">
                          {c.document_code}
                        </span>
                      )}
                      {c.aircraft_model && (
                        <span>aircraft · {c.aircraft_model}</span>
                      )}
                      {c.component && <span>component · {c.component}</span>}
                      {c.ata && c.ata.length > 0 && (
                        <span>ATA · {c.ata.join(", ")}</span>
                      )}
                      {c.vendor && <span>vendor · {c.vendor}</span>}
                    </div>
                    <blockquote className="mt-2 border-l-2 border-white/10 pl-3 text-[12px] italic leading-relaxed text-ink-300 group-hover:border-cyan-500/50">
                      {c.snippet}
                    </blockquote>
                    {c.url && (
                      <a
                        href={c.url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 inline-block max-w-full truncate text-[11px] text-cyan-300 hover:underline"
                      >
                        {c.url}
                      </a>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <div className="font-mono text-[12px] text-cyan-300">
                      {c.score.toFixed(2)}
                    </div>
                    <div className="label-eyebrow">score</div>
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
