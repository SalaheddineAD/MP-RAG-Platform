export function formatMs(ms: number | undefined | null): string {
  if (ms == null || Number.isNaN(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatUsd(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (value < 0.01) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(3)}`;
}

export function formatScore(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(3);
}

export function formatPercent(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

export function scoreTone(value: number): "good" | "warn" | "bad" {
  if (value >= 0.85) return "good";
  if (value >= 0.7) return "warn";
  return "bad";
}
