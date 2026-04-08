"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";
import type { JobCreateRequest, JobRecord, JobStatus } from "@/lib/types";

const AIRCRAFT_OPTIONS = [
  "Phenom 300",
  "Citation XLS",
  "King Air 350",
  "Gulfstream G200",
  "Learjet 60",
  "Other",
];

type SubmitState =
  | { kind: "idle" }
  | { kind: "sending" }
  | { kind: "ok"; job: JobRecord }
  | { kind: "error"; message: string };

export function CreateJobForm() {
  const router = useRouter();

  const [aircraft, setAircraft] = useState(AIRCRAFT_OPTIONS[0]);
  const [tailNumber, setTailNumber] = useState("");
  const [discrepancy, setDiscrepancy] = useState("");
  const [ata, setAta] = useState("");
  const [symptoms, setSymptoms] = useState("");
  const [actions, setActions] = useState("");
  const [parts, setParts] = useState("");
  const [corrective, setCorrective] = useState("");
  const [technician, setTechnician] = useState("");
  const [notes, setNotes] = useState("");
  const [workOrder, setWorkOrder] = useState("");
  const [status, setStatus] = useState<JobStatus>("closed");
  const [submit, setSubmit] = useState<SubmitState>({ kind: "idle" });

  const reset = () => {
    setTailNumber("");
    setDiscrepancy("");
    setAta("");
    setSymptoms("");
    setActions("");
    setParts("");
    setCorrective("");
    setTechnician("");
    setNotes("");
    setWorkOrder("");
    setStatus("closed");
    setSubmit({ kind: "idle" });
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (discrepancy.trim().length < 5) {
      setSubmit({
        kind: "error",
        message: "Discrepancy must be at least 5 characters.",
      });
      return;
    }
    setSubmit({ kind: "sending" });
    const payload: JobCreateRequest = {
      aircraft,
      tail_number: tailNumber || undefined,
      discrepancy,
      ata: ata || undefined,
      symptoms: symptoms || undefined,
      actions_taken: actions || undefined,
      parts_replaced: parts
        .split(/[\n,]/)
        .map((p) => p.trim())
        .filter(Boolean),
      corrective_action: corrective || undefined,
      technician: technician || undefined,
      technician_notes: notes || undefined,
      work_order: workOrder || undefined,
      status,
    };
    try {
      const job = await api.createJob(payload);
      setSubmit({ kind: "ok", job });
      // Refresh the server-rendered list.
      router.refresh();
    } catch (err) {
      setSubmit({
        kind: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    }
  };

  return (
    <Card
      title="Log a new discrepancy"
      subtitle="Each record becomes a HISTORY-family source and participates in federation"
      action={<span className="pill-cyan">shop memory</span>}
    >
      <form onSubmit={onSubmit} className="space-y-3 text-[12.5px]">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Aircraft">
            <select
              value={aircraft}
              onChange={(e) => setAircraft(e.target.value)}
              className={inputClass}
            >
              {AIRCRAFT_OPTIONS.map((a) => (
                <option key={a}>{a}</option>
              ))}
            </select>
          </Field>
          <Field label="Tail number">
            <input
              value={tailNumber}
              onChange={(e) => setTailNumber(e.target.value)}
              placeholder="N512TG"
              className={inputClass}
            />
          </Field>
        </div>
        <Field label="Discrepancy">
          <textarea
            value={discrepancy}
            onChange={(e) => setDiscrepancy(e.target.value)}
            rows={2}
            required
            placeholder="TOGA lever button unresponsive on captain side..."
            className={inputClass}
          />
        </Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="ATA">
            <input
              value={ata}
              onChange={(e) => setAta(e.target.value)}
              placeholder="22"
              className={inputClass}
            />
          </Field>
          <Field label="Work order">
            <input
              value={workOrder}
              onChange={(e) => setWorkOrder(e.target.value)}
              placeholder="WO-2026-0418"
              className={inputClass}
            />
          </Field>
          <Field label="Status">
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as JobStatus)}
              className={inputClass}
            >
              <option value="open">open</option>
              <option value="in_progress">in progress</option>
              <option value="closed">closed</option>
            </select>
          </Field>
        </div>
        <Field label="Symptoms">
          <textarea
            value={symptoms}
            onChange={(e) => setSymptoms(e.target.value)}
            rows={2}
            placeholder="What the crew / mechanic observed"
            className={inputClass}
          />
        </Field>
        <Field label="Actions taken">
          <textarea
            value={actions}
            onChange={(e) => setActions(e.target.value)}
            rows={2}
            placeholder="Steps worked during troubleshooting"
            className={inputClass}
          />
        </Field>
        <Field label="Parts replaced">
          <input
            value={parts}
            onChange={(e) => setParts(e.target.value)}
            placeholder="011-03035-10, 011-03036-10"
            className={inputClass}
          />
        </Field>
        <Field label="Corrective action">
          <textarea
            value={corrective}
            onChange={(e) => setCorrective(e.target.value)}
            rows={2}
            placeholder="What fixed the aircraft"
            className={inputClass}
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Technician">
            <input
              value={technician}
              onChange={(e) => setTechnician(e.target.value)}
              placeholder="J. Mero"
              className={inputClass}
            />
          </Field>
          <Field label="Notes">
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Return-to-service notes, recurring flag, etc."
              className={inputClass}
            />
          </Field>
        </div>
        <div className="flex items-center justify-between gap-2 pt-1">
          <button
            type="submit"
            disabled={submit.kind === "sending"}
            className="rounded-lg border border-cyan-400/50 bg-cyan-500/[0.08] px-3 py-1.5 text-[12px] font-medium text-cyan-200 hover:bg-cyan-500/[0.14] disabled:opacity-50"
          >
            {submit.kind === "sending" ? "Logging…" : "Log discrepancy"}
          </button>
          <button
            type="button"
            onClick={reset}
            className="text-[11px] uppercase tracking-[0.12em] text-ink-400 hover:text-ink-200"
          >
            clear
          </button>
        </div>
        {submit.kind === "ok" && (
          <div className="rounded-md border border-emerald-400/30 bg-emerald-500/[0.06] px-3 py-2 text-[11.5px] text-emerald-200">
            Logged as <code className="mono-meta">{submit.job.id}</code>.
            Indexed {submit.job.chunk_count} chunk(s) as{" "}
            <span className="font-mono">HISTORY</span>. Ask Topgun AI a
            related question to see it surface.
          </div>
        )}
        {submit.kind === "error" && (
          <div className="rounded-md border border-rose-400/30 bg-rose-500/[0.06] px-3 py-2 text-[11.5px] text-rose-200">
            {submit.message}
          </div>
        )}
      </form>
    </Card>
  );
}

const inputClass =
  "w-full rounded-lg border border-white/[0.08] bg-gunmetal-900/70 px-3 py-1.5 text-ink-100 placeholder:text-ink-500 focus:border-cyan-400/40 focus:outline-none";

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="label-eyebrow mb-1">{label}</div>
      {children}
    </div>
  );
}
