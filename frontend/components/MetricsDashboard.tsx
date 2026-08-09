"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchMetrics } from "@/lib/api";
import { formatMs, formatUsd } from "@/lib/format";
import type { PlatformMetrics } from "@/lib/types";

export function MetricsDashboard() {
  const [metrics, setMetrics] = useState<PlatformMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchMetrics();
      setMetrics(data);
      setError(null);
      setUpdatedAt(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load metrics");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = window.setInterval(load, 10000);
    return () => window.clearInterval(id);
  }, [load]);

  return (
    <div className="flex flex-col gap-10">
      <section className="fade-up flex flex-col gap-4">
        <p className="font-mono text-[11px] tracking-[0.28em] text-accent uppercase">
          Telemetry
        </p>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <h1 className="text-4xl font-medium tracking-tight text-ink md:text-5xl">
            Platform metrics.
          </h1>
          <button
            type="button"
            onClick={() => {
              setLoading(true);
              load();
            }}
            className="border border-line px-4 py-2 text-sm text-ink-muted transition hover:border-accent hover:text-ink"
          >
            Refresh
          </button>
        </div>
        <p className="max-w-xl text-base leading-relaxed text-ink-muted md:text-lg">
          Live cost and latency from the FastAPI cost tracker. Refreshes every
          10 seconds while this page is open.
        </p>
      </section>

      {error ? (
        <div className="fade-up border-l-2 border-bad bg-bg-elevated px-4 py-3 text-sm text-bad">
          {error}
        </div>
      ) : null}

      <section className="fade-up-delay grid gap-px border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
        <MetricTile
          label="Total queries"
          value={loading && !metrics ? "…" : String(metrics?.total_queries ?? 0)}
        />
        <MetricTile
          label="Total cost"
          value={loading && !metrics ? "…" : formatUsd(metrics?.total_cost_usd ?? 0)}
        />
        <MetricTile
          label="Today's cost"
          value={loading && !metrics ? "…" : formatUsd(metrics?.today_cost_usd ?? 0)}
        />
        <MetricTile
          label="Avg latency"
          value={loading && !metrics ? "…" : formatMs(metrics?.avg_latency_ms ?? 0)}
        />
        <MetricTile
          label="P95 latency"
          value={loading && !metrics ? "…" : formatMs(metrics?.p95_latency_ms ?? 0)}
        />
        <MetricTile
          label="Avg cost / query"
          value={
            loading && !metrics ? "…" : formatUsd(metrics?.avg_cost_per_query ?? 0)
          }
        />
        <MetricTile
          label="Budget remaining"
          value={
            loading && !metrics
              ? "…"
              : formatUsd(metrics?.budget_remaining_usd ?? metrics?.daily_budget_usd ?? 0)
          }
        />
        <MetricTile
          label="Budget status"
          value={
            loading && !metrics
              ? "…"
              : metrics?.budget_exceeded
                ? "Exceeded"
                : "Within limit"
          }
        />
        <MetricTile
          label="Last updated"
          value={
            updatedAt
              ? updatedAt.toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })
              : "—"
          }
        />
      </section>
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-bg-elevated px-5 py-6">
      <p className="font-mono text-[11px] tracking-[0.16em] text-ink-muted uppercase">
        {label}
      </p>
      <p className="mt-3 font-mono text-3xl tracking-tight text-ink">{value}</p>
    </div>
  );
}
