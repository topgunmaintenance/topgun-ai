import { AppShell } from "@/components/layout/AppShell";
import { CreateJobForm } from "@/components/history/CreateJobForm";
import { JobList } from "@/components/history/JobList";
import { safeListJobs } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HistoryPage() {
  const list = await safeListJobs();
  const closed = list.jobs.filter((j) => j.status === "closed").length;
  const open = list.jobs.filter(
    (j) => j.status === "open" || j.status === "in_progress",
  ).length;

  return (
    <AppShell subtitle="History / Jobs">
      <header className="mb-7 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="pill mb-3">Shop memory</div>
          <h1 className="text-[30px] font-semibold leading-tight tracking-[-0.015em] text-ink-100 md:text-[38px]">
            Every discrepancy, searchable the next time it happens.
          </h1>
          <p className="mt-2 max-w-2xl text-[13.5px] leading-relaxed text-ink-300">
            Log a discrepancy, corrective action, and parts replaced.
            Each record is indexed into the HISTORY source family and
            participates in federated retrieval — so the next
            troubleshooting query against the same symptom surfaces
            what the shop has seen before.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="pill">{list.total} jobs</span>
          {closed > 0 && <span className="pill-emerald">{closed} closed</span>}
          {open > 0 && <span className="pill-amber">{open} open</span>}
        </div>
      </header>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <JobList jobs={list.jobs} />
        </div>
        <div className="space-y-5">
          <CreateJobForm />
        </div>
      </div>
    </AppShell>
  );
}
