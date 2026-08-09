"use client";

import { FormEvent, useState } from "react";
import { queryKnowledgeBase } from "@/lib/api";
import { formatMs, formatUsd } from "@/lib/format";
import type { ChunkStrategy, QueryResponse } from "@/lib/types";
import { checkboxRowClass, controlClass, Field } from "@/components/Field";

const examples = [
  "What is the torque specification for the battery mount?",
  "How fast can a stamped steel body part be produced?",
  "What crush distance is typical in a 35 mph frontal impact?",
];

export function QueryConsole() {
  const [question, setQuestion] = useState("");
  const [namespace, setNamespace] = useState("battery_line_1");
  const [strategy, setStrategy] = useState<ChunkStrategy>("recursive");
  const [useHybrid, setUseHybrid] = useState(true);
  const [useRerank, setUseRerank] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QueryResponse | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const data = await queryKnowledgeBase({
        question: question.trim(),
        namespace,
        strategy,
        useHybrid,
        useRerank,
      });
      setResult(data);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Query failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-10">
      <section className="fade-up flex flex-col gap-5">
        <p className="font-mono text-[11px] tracking-[0.28em] text-accent uppercase">
          Manufacturing RAG
        </p>
        <h1 className="max-w-3xl text-4xl leading-[1.05] font-medium tracking-tight text-ink md:text-5xl">
          Ask the line documentation.
        </h1>
        <p className="max-w-xl text-base leading-relaxed text-ink-muted md:text-lg">
          Hybrid retrieval with citations, cost metering, and grounded answers
          from your manufacturing knowledge base.
        </p>
      </section>

      <form
        onSubmit={onSubmit}
        className="fade-up-delay flex flex-col gap-5 border-y border-line bg-bg-elevated/90 py-6"
      >
        <Field label="Question">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={3}
            placeholder="Ask about torque specs, procedures, materials…"
            className={`${controlClass} min-h-[96px] resize-y`}
            required
          />
        </Field>

        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Namespace" hint="Pinecone tenant isolation">
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
          <div className="flex flex-col justify-end gap-3 pb-1">
            <label className={checkboxRowClass}>
              <input
                type="checkbox"
                checked={useHybrid}
                onChange={(e) => setUseHybrid(e.target.checked)}
                className="accent-accent"
              />
              Hybrid search (dense + BM25)
            </label>
            <label className={checkboxRowClass}>
              <input
                type="checkbox"
                checked={useRerank}
                onChange={(e) => setUseRerank(e.target.checked)}
                className="accent-accent"
              />
              Cross-encoder rerank
            </label>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={loading || !question.trim()}
            className={`bg-accent px-5 py-2.5 text-sm font-medium text-white transition hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50 ${
              loading ? "pulse-ring" : ""
            }`}
          >
            {loading ? "Retrieving…" : "Run query"}
          </button>
          <span className="font-mono text-xs tracking-wide text-ink-muted uppercase">
            Avg cost ~$0.003 · P95 ~590 ms
          </span>
        </div>

        <div className="flex flex-wrap gap-2">
          {examples.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => setQuestion(example)}
              className="border border-line px-3 py-1.5 text-left text-xs text-ink-muted transition hover:border-accent hover:text-ink"
            >
              {example}
            </button>
          ))}
        </div>
      </form>

      {error ? (
        <div className="fade-up border-l-2 border-bad bg-bg-elevated px-4 py-3 text-sm text-bad">
          {error}
        </div>
      ) : null}

      {result ? (
        <section className="fade-up flex flex-col gap-6">
          <div>
            <p className="mb-3 font-mono text-[11px] tracking-[0.16em] text-ink-muted uppercase">
              Answer
            </p>
            <p className="text-lg leading-relaxed whitespace-pre-wrap text-ink">
              {result.answer}
            </p>
          </div>

          <div className="grid gap-3 border-t border-line pt-5 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Latency" value={formatMs(result.metrics.total_latency_ms)} />
            <Metric label="Retrieval" value={formatMs(result.metrics.retrieval_latency_ms)} />
            <Metric label="Generation" value={formatMs(result.metrics.generation_latency_ms)} />
            <Metric label="Cost" value={formatUsd(result.metrics.total_cost_usd)} />
          </div>

          <div className="grid gap-6 border-t border-line pt-5 md:grid-cols-2">
            <div>
              <p className="mb-3 font-mono text-[11px] tracking-[0.16em] text-ink-muted uppercase">
                Sources
              </p>
              {result.sources.length === 0 ? (
                <p className="text-sm text-ink-muted">No sources returned.</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {result.sources.map((source, index) => (
                    <li
                      key={`${source.source}-${source.chunk_index}-${index}`}
                      className="flex items-baseline justify-between gap-3 border-b border-line/70 py-2 text-sm"
                    >
                      <span className="truncate text-ink">{source.source}</span>
                      <span className="font-mono text-xs text-ink-muted">
                        chunk {source.chunk_index}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <p className="mb-3 font-mono text-[11px] tracking-[0.16em] text-ink-muted uppercase">
                Pipeline
              </p>
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-ink-muted">Retrieval</dt>
                  <dd className="font-mono text-ink">
                    {result.retrieval_strategy ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-muted">Chunking</dt>
                  <dd className="font-mono text-ink">
                    {result.chunking_strategy ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-muted">Input tokens</dt>
                  <dd className="font-mono text-ink">
                    {result.metrics.input_tokens ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-muted">Output tokens</dt>
                  <dd className="font-mono text-ink">
                    {result.metrics.output_tokens ?? "—"}
                  </dd>
                </div>
              </dl>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="font-mono text-[11px] tracking-[0.14em] text-ink-muted uppercase">
        {label}
      </p>
      <p className="mt-1 font-mono text-xl text-ink">{value}</p>
    </div>
  );
}
