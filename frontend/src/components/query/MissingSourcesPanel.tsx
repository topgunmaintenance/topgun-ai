import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import type { CoverageReport, SourceFamily } from "@/lib/types";

const FAMILY_GLYPH: Record<SourceFamily, string> = {
  FIM: "FIM",
  WDM: "WDM",
  AMM: "AMM",
  IPC: "IPC",
  SB: "SB",
  HISTORY: "HX",
  BROWSER: "WB",
  EXTERNAL: "EXT",
  OTHER: "—",
};

export function MissingSourcesPanel({
  coverage,
}: {
  coverage?: CoverageReport | null;
}) {
  const gaps = coverage?.gaps ?? [];
  return (
    <Card
      title="Missing likely sources"
      subtitle="Recommended manuals to connect for higher confidence"
      action={
        gaps.length > 0 ? (
          <span className="pill rounded-full border-amber-400/40 bg-amber-500/[0.08] text-amber-200">
            {gaps.length} gap{gaps.length === 1 ? "" : "s"}
          </span>
        ) : (
          <span className="pill rounded-full border-emerald-400/40 bg-emerald-500/[0.08] text-emerald-200">
            full coverage
          </span>
        )
      }
    >
      {gaps.length === 0 ? (
        <EmptyState
          glyph="✓"
          title="All likely source families are connected"
          body="Topgun AI has at least one document indexed for every source family the intent classifier predicted for this question."
        />
      ) : (
        <ul className="space-y-3">
          {gaps.map((gap) => (
            <li
              key={gap.family}
              className="rounded-xl border border-amber-400/25 bg-amber-500/[0.04] p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="rounded-md border border-amber-400/40 px-1.5 py-[1px] font-mono text-[10px] uppercase tracking-[0.1em] text-amber-200">
                      {FAMILY_GLYPH[gap.family]}
                    </span>
                    <span className="text-[13px] font-medium text-ink-100">
                      {gap.label}
                    </span>
                  </div>
                  <p className="mt-2 text-[12.5px] leading-relaxed text-ink-300">
                    {gap.reason}
                  </p>
                  {gap.vendor_hint && (
                    <div className="mt-2 text-[11.5px] text-amber-200/90">
                      Suggested: {gap.vendor_hint}
                    </div>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
      {coverage && (
        <div className="mt-4 grid grid-cols-2 gap-3 text-[11px] text-ink-400">
          <div>
            <div className="label-eyebrow">Likely needed</div>
            <div className="mt-1 flex flex-wrap gap-1">
              {coverage.likely_families.map((f) => (
                <span key={f} className="pill mono-meta">
                  {f}
                </span>
              ))}
            </div>
          </div>
          <div>
            <div className="label-eyebrow">Connected</div>
            <div className="mt-1 flex flex-wrap gap-1">
              {coverage.available_families.length === 0 ? (
                <span className="pill mono-meta text-ink-500">none</span>
              ) : (
                coverage.available_families.map((f) => (
                  <span
                    key={f}
                    className="pill mono-meta border-emerald-400/30 text-emerald-200"
                  >
                    {f}
                  </span>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
