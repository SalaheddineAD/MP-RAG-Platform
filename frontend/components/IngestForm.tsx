"use client";

import { FormEvent, useRef, useState } from "react";
import { ingestDocument } from "@/lib/api";
import { formatMs } from "@/lib/format";
import type { ChunkStrategy, IngestResponse } from "@/lib/types";
import { controlClass, Field } from "@/components/Field";

export function IngestForm() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [namespace, setNamespace] = useState("battery_line_1");
  const [strategy, setStrategy] = useState<ChunkStrategy>("recursive");
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IngestResponse | null>(null);

  function acceptFile(next: File | null | undefined) {
    if (!next) return;
    setFile(next);
    setResult(null);
    setError(null);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("Choose a document to ingest.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await ingestDocument({ file, namespace, strategy });
      setResult(data);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Ingestion failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-10">
      <section className="fade-up flex flex-col gap-4">
        <p className="font-mono text-[11px] tracking-[0.28em] text-accent uppercase">
          Document intake
        </p>
        <h1 className="text-4xl font-medium tracking-tight text-ink md:text-5xl">
          Ingest manufacturing docs.
        </h1>
        <p className="max-w-xl text-base leading-relaxed text-ink-muted md:text-lg">
          Upload PDF, text, or markdown into an isolated namespace. Chunking
          strategy is recorded with every upsert.
        </p>
      </section>

      <form
        onSubmit={onSubmit}
        className="fade-up-delay flex flex-col gap-6 border-y border-line bg-bg-elevated/90 py-6"
      >
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            acceptFile(e.dataTransfer.files?.[0]);
          }}
          onClick={() => inputRef.current?.click()}
          className={`cursor-pointer border border-dashed px-6 py-14 text-center transition ${
            dragOver
              ? "border-accent bg-accent-soft/50"
              : "border-line hover:border-accent/60"
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            accept=".pdf,.txt,.md,.markdown,.csv"
            onChange={(e) => acceptFile(e.target.files?.[0])}
          />
          <p className="text-base text-ink">
            {file ? file.name : "Drop a document here, or click to browse"}
          </p>
          <p className="mt-2 font-mono text-xs tracking-wide text-ink-muted uppercase">
            PDF · TXT · Markdown
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Namespace">
            <input
              value={namespace}
              onChange={(e) => setNamespace(e.target.value)}
              className={controlClass}
              required
            />
          </Field>
          <Field label="Chunk strategy">
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as ChunkStrategy)}
              className={controlClass}
            >
              <option value="recursive">Recursive</option>
              <option value="semantic">Semantic</option>
              <option value="agentic">Agentic</option>
            </select>
          </Field>
        </div>

        <button
          type="submit"
          disabled={loading || !file}
          className={`w-fit bg-accent px-5 py-2.5 text-sm font-medium text-white transition hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50 ${
            loading ? "pulse-ring" : ""
          }`}
        >
          {loading ? "Embedding…" : "Ingest document"}
        </button>
      </form>

      {error ? (
        <div className="fade-up border-l-2 border-bad bg-bg-elevated px-4 py-3 text-sm text-bad">
          {error}
        </div>
      ) : null}

      {result ? (
        <section className="fade-up border-t border-line pt-6">
          <p className="mb-4 font-mono text-[11px] tracking-[0.16em] text-good uppercase">
            Ingest complete
          </p>
          <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="File" value={result.filename} />
            <Stat label="Chunks" value={String(result.chunks_created)} />
            <Stat label="Namespace" value={result.namespace} />
            <Stat label="Time" value={formatMs(result.ingestion_time_ms)} />
          </dl>
        </section>
      ) : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-mono text-[11px] tracking-[0.14em] text-ink-muted uppercase">
        {label}
      </dt>
      <dd className="mt-1 break-all font-mono text-lg text-ink">{value}</dd>
    </div>
  );
}
