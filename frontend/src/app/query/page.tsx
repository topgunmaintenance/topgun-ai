import { AppShell } from "@/components/layout/AppShell";
import { AnswerPanel } from "@/components/query/AnswerPanel";
import { BrowserPushCard } from "@/components/query/BrowserPushCard";
import { CitationsPanel } from "@/components/query/CitationsPanel";
import { EntitiesPanel } from "@/components/query/EntitiesPanel";
import { FollowupPrompts } from "@/components/query/FollowupPrompts";
import { IntentPanel } from "@/components/query/IntentPanel";
import { MissingSourcesPanel } from "@/components/query/MissingSourcesPanel";
import { PriorSimilarJobsPanel } from "@/components/query/PriorSimilarJobsPanel";
import { QueryInput } from "@/components/query/QueryInput";
import { RelatedDocsPanel } from "@/components/query/RelatedDocsPanel";
import { SessionHeader } from "@/components/query/SessionHeader";
import { SourceDrawerPreview } from "@/components/query/SourceDrawerPreview";
import { api } from "@/lib/api";
import { demoData } from "@/lib/demoData";
import type { QueryResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

const DEFAULT_QUESTION =
  "TOGA lever button not working on a Phenom 300";

async function loadAnswer(): Promise<QueryResponse> {
  try {
    return await api.ask(DEFAULT_QUESTION);
  } catch {
    return demoData.exampleQueryResponse;
  }
}

export default async function QueryWorkspacePage() {
  const response = await loadAnswer();
  const topCitation = response.citations[0];

  return (
    <AppShell subtitle="Query Workspace">
      <header className="mb-8">
        <div className="pill-cyan mb-3">
          <span className="h-1.5 w-1.5 rounded-full bg-cyan-300" />
          Intelligence panel · mission-critical
        </div>
        <h1 className="text-[30px] font-semibold leading-tight tracking-[-0.015em] text-ink-100 md:text-[38px]">
          Federate FIM, AMM, IPC, WDM, SB, history, and your authenticated
          browser — in one query.
        </h1>
        <p className="mt-2 max-w-2xl text-[13.5px] leading-relaxed text-ink-300">
          Every answer is grouped by source family, scored, and labeled
          when evidence is weak. If a likely manual isn&apos;t connected,
          Topgun AI says so explicitly instead of guessing.
        </p>
      </header>

      <QueryInput initialQuestion={response.question} />

      <div className="mt-6">
        <SessionHeader
          question={response.question}
          latencyMs={response.latency_ms}
          provider="stub"
          citationCount={response.citations.length}
          confidenceLabel={response.confidence.label}
        />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <AnswerPanel response={response} />
          <PriorSimilarJobsPanel jobs={response.prior_similar_jobs} />
          <MissingSourcesPanel coverage={response.coverage} />
          <CitationsPanel citations={response.citations} />
        </div>
        <div className="space-y-5">
          <IntentPanel intent={response.intent} />
          <BrowserPushCard />
          <SourceDrawerPreview citation={topCitation} />
          <EntitiesPanel entities={response.entities} />
          <RelatedDocsPanel docs={response.related_documents} />
          <FollowupPrompts prompts={response.followups} />
        </div>
      </div>
    </AppShell>
  );
}
