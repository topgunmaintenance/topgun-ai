"use client";

import { useState } from "react";

import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";

export function BrowserPushCard() {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [vendor, setVendor] = useState("");
  const [aircraft, setAircraft] = useState("");
  const [text, setText] = useState("");
  const [status, setStatus] = useState<
    | { kind: "idle" }
    | { kind: "sending" }
    | { kind: "ok"; doc_id: string }
    | { kind: "error"; message: string }
  >({ kind: "idle" });

  const reset = () => {
    setTitle("");
    setUrl("");
    setVendor("");
    setAircraft("");
    setText("");
    setStatus({ kind: "idle" });
  };

  const submit = async () => {
    if (!title.trim() || text.trim().length < 10) {
      setStatus({
        kind: "error",
        message: "Title and at least 10 characters of text are required.",
      });
      return;
    }
    setStatus({ kind: "sending" });
    try {
      const result = await api.pushBrowserPage({
        title,
        text,
        url: url || undefined,
        vendor: vendor || undefined,
        aircraft: aircraft || undefined,
      });
      setStatus({ kind: "ok", doc_id: result.doc_id });
    } catch (e) {
      setStatus({
        kind: "error",
        message: e instanceof Error ? e.message : String(e),
      });
    }
  };

  return (
    <Card
      title="Push from authenticated browser"
      subtitle="Send a manual page from your dedicated browser into Topgun AI"
      action={
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="pill-cyan"
        >
          {open ? "hide" : "open"}
        </button>
      }
    >
      <p className="text-[12px] leading-relaxed text-ink-300">
        Topgun AI never scrapes the open internet. Use your browser
        extension or local helper to push the visible page from a portal
        you&apos;re already signed into. The push hits{" "}
        <code className="mono-meta">/api/connectors/browser/push</code> and
        the result is indexed as a <span className="font-mono">BROWSER</span>{" "}
        source family ready for federation.
      </p>

      {open && (
        <div className="mt-4 space-y-3 text-[12.5px]">
          <Field label="Title" value={title} onChange={setTitle} />
          <Field
            label="URL"
            value={url}
            onChange={setUrl}
            placeholder="https://garmin-portal.example.com/..."
          />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Vendor" value={vendor} onChange={setVendor} />
            <Field label="Aircraft" value={aircraft} onChange={setAircraft} />
          </div>
          <div>
            <div className="label-eyebrow mb-1">Page text</div>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={6}
              className="w-full rounded-lg border border-white/[0.08] bg-gunmetal-900/70 p-3 font-mono text-[11.5px] text-ink-100 focus:border-cyan-400/40 focus:outline-none"
              placeholder="Paste the visible page text from the authenticated browser tab..."
            />
          </div>
          <div className="flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={submit}
              disabled={status.kind === "sending"}
              className="rounded-lg border border-cyan-400/50 bg-cyan-500/[0.08] px-3 py-1.5 text-[12px] font-medium text-cyan-200 hover:bg-cyan-500/[0.14] disabled:opacity-50"
            >
              {status.kind === "sending" ? "Pushing…" : "Push to Topgun AI"}
            </button>
            <button
              type="button"
              onClick={reset}
              className="text-[11px] uppercase tracking-[0.12em] text-ink-400 hover:text-ink-200"
            >
              clear
            </button>
          </div>
          {status.kind === "ok" && (
            <div className="rounded-md border border-emerald-400/30 bg-emerald-500/[0.06] px-3 py-2 text-[11.5px] text-emerald-200">
              Indexed as <code className="mono-meta">{status.doc_id}</code>.
              Re-run the query to see it in the federation.
            </div>
          )}
          {status.kind === "error" && (
            <div className="rounded-md border border-rose-400/30 bg-rose-500/[0.06] px-3 py-2 text-[11.5px] text-rose-200">
              {status.message}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div>
      <div className="label-eyebrow mb-1">{label}</div>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-white/[0.08] bg-gunmetal-900/70 px-3 py-1.5 text-ink-100 focus:border-cyan-400/40 focus:outline-none"
      />
    </div>
  );
}
