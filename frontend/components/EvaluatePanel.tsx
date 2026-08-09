"use client";

import { FormEvent, useState } from "react";
import { runEvaluation } from "@/lib/api";
import { formatMs, formatPercent, formatScore, formatUsd, scoreTone } from "@/lib/format";
import type { EvaluateResponse } from "@/lib/types";
import { checkboxRowClass, controlClass, Field } from "@/components/Field";

export function EvaluatePanel() {
  const [namespace, setNamespace] = useState("battery_line_1");
  const [goldenSet, setGoldenSet] = useState("data/golden_set/golden_set.jsonl");
  const [useLlmJudge, setUseLlmJudge] = useState(true);
  const [saveResults, setSaveResults] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EvaluateResponse | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const data = await runEvaluation({
        namespace,
        goldenSet,
        useLlmJudge,
        saveResults,
      });
      setResult(data);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Evaluation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-10">
      <section className="fade-up flex flex-col gap-4">
        <p className="font-mono text-[11px] tracking-[0.28em] text-accent uppercase">
          Quality gate
        </p>
        <h1 className="text-4xl font-medium tracking-tight text-ink md:text-5xl">
          Run golden-set eval.
        </h1>
        <p className="max-w-xl text-base leading-relaxed text-ink-muted md:text-lg">
          Measure faithfulness, answer correctness, relevance, and context
          precision against your held-out manufacturing Q&A set.
        </p>
      </section>

      <form
        onSubmit={onSubmit}
        className="fade-up-delay flex flex-col gap-5 border-y border-line bg-bg-elevated/90 py-6"
      >
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Namespace">
            <input
              value={namespace}
              onChange={(e) => setNamespace(e.target.value)}
              className={controlClass}
              required
            />
          </Field>
          <Field label="Golden set path">
            <input
              value={goldenSet}
              onChange={(e) => setGoldenSet(e.target.value)}
              className={controlClass}
              required
            />
          </Field>
        </div>

        <div className="flex flex-wrap gap-6">
          <label className={checkboxRowClass}>
            <input
              type="checkbox"
              checked={useLlmJudge}
              onChange={(e) => setUseLlmJudge(e.target.checked)}
              className="accent-accent"
            />
            Use LLM judge
          </label>
          <label className={checkboxRowClass}>
            <input
              type="checkbox"
              checked={saveResults}
              onChange={(e) => setSaveResults(e.target.checked)}
              className="accent-accent"
            />
            Save results to disk
          </label>
        </div>

        <button
          type="submit"
          disabled={loading}
          className={`w-fit bg-accent px-5 py-2.5 text-sm font-medium text-white transition hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50 ${
            loading ? "pulse-ring" : ""
          }`}
        >
          {loading ? "Evaluating… this can take a minute" : "Start evaluation"}
        </button>
      </form>

      {error ? (
        <div className="fade-up border-l-2 border-bad bg-bg-elevated px-4 py-3 text-sm text-bad">
          {error}
        </div>
      ) : null}

      {result ? <EvalResults result={result} /> : null}
    </div>
  );
}

function EvalResults({ result }: { result: EvaluateResponse }) {
  const { summary, by_difficulty, failed_queries } = result;

  return (
    <section className="fade-up flex flex-col gap-8">
      <div>
        <p className="mb-4 font-mono text-[11px] tracking-[0.16em] text-ink-muted uppercase">
          Summary · {summary.total_evaluated} queries · {result.total_failures}{" "}
          flagged
        </p>
        <div className="grid gap-px border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
          <ScoreTile label="Faithfulness" value={summary.avg_faithfulness} />
          <ScoreTile label="Correctness" value={summary.avg_answer_correctness} />
          <ScoreTile label="Relevance" value={summary.avg_answer_relevance} />
          <ScoreTile label="Context precision" value={summary.avg_context_precision} />
          <PlainTile label="Avg latency" value={formatMs(summary.avg_latency_ms)} />
          <PlainTile label="Total cost" value={formatUsd(summary.total_cost_usd)} />
        </div>
        {result.saved_to ? (
          <p className="mt-3 font-mono text-xs text-ink-muted">
            Saved to {result.saved_to}
          </p>
        ) : null}
      </div>

      <div>
        <p className="mb-4 font-mono text-[11px] tracking-[0.16em] text-ink-muted uppercase">
          By difficulty
        </p>
        <div className="overflow-x-auto border border-line">
          <table className="w-full min-w-[640px] border-collapse text-left text-sm">
            <thead className="bg-bg-elevated font-mono text-[11px] tracking-[0.12em] text-ink-muted uppercase">
              <tr>
                <th className="px-4 py-3 font-medium">Level</th>
                <th className="px-4 py-3 font-medium">Count</th>
                <th className="px-4 py-3 font-medium">Faithfulness</th>
                <th className="px-4 py-3 font-medium">Correctness</th>
                <th className="px-4 py-3 font-medium">Relevance</th>
                <th className="px-4 py-3 font-medium">Precision</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(by_difficulty).map(([level, row]) => (
                <tr key={level} className="border-t border-line">
                  <td className="px-4 py-3 capitalize">{level}</td>
                  <td className="px-4 py-3 font-mono">{row.count}</td>
                  <td className="px-4 py-3 font-mono">{formatScore(row.faithfulness)}</td>
                  <td className="px-4 py-3 font-mono">
                    {formatScore(row.answer_correctness)}
                  </td>
                  <td className="px-4 py-3 font-mono">{formatScore(row.relevance)}</td>
                  <td className="px-4 py-3 font-mono">{formatScore(row.precision)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {failed_queries.length > 0 ? (
        <div>
          <p className="mb-4 font-mono text-[11px] tracking-[0.16em] text-ink-muted uppercase">
            Flagged queries
          </p>
          <ul className="flex flex-col gap-4">
            {failed_queries.map((item, index) => (
              <li
                key={`${item.question}-${index}`}
                className="border-t border-line pt-4 first:border-t-0 first:pt-0"
              >
                <p className="text-sm font-medium text-ink">{item.question}</p>
                <p className="mt-2 text-sm text-ink-muted">{item.reason}</p>
                <div className="mt-3 grid gap-3 text-xs text-ink-muted md:grid-cols-3">
                  <p>
                    <span className="font-mono uppercase tracking-wide">Expected</span>
                    <br />
                    <span className="text-ink">{item.expected}</span>
                  </p>
                  <p>
                    <span className="font-mono uppercase tracking-wide">Generated</span>
                    <br />
                    <span className="text-ink">{item.generated}</span>
                  </p>
                  <p className="font-mono">
                    F {formatPercent(item.faithfulness)} · C{" "}
                    {formatPercent(item.answer_correctness)} · R{" "}
                    {formatPercent(item.relevance)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function ScoreTile({ label, value }: { label: string; value: number }) {
  const tone = scoreTone(value);
  const color =
    tone === "good" ? "text-good" : tone === "warn" ? "text-warn" : "text-bad";

  return (
    <div className="bg-bg-elevated px-5 py-5">
      <p className="font-mono text-[11px] tracking-[0.14em] text-ink-muted uppercase">
        {label}
      </p>
      <p className={`mt-2 font-mono text-3xl ${color}`}>{formatScore(value)}</p>
    </div>
  );
}

function PlainTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-bg-elevated px-5 py-5">
      <p className="font-mono text-[11px] tracking-[0.14em] text-ink-muted uppercase">
        {label}
      </p>
      <p className="mt-2 font-mono text-3xl text-ink">{value}</p>
    </div>
  );
}
