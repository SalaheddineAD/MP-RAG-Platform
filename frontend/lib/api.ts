import type {
  EvaluateResponse,
  HealthResponse,
  IngestResponse,
  PlatformMetrics,
  QueryResponse,
} from "./types";

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    if (typeof data?.error === "string") return data.error;
    return JSON.stringify(data);
  } catch {
    return res.statusText || `Request failed (${res.status})`;
  }
}

export async function queryKnowledgeBase(params: {
  question: string;
  namespace: string;
  strategy: string;
  useHybrid: boolean;
  useRerank: boolean;
}): Promise<QueryResponse> {
  const body = new FormData();
  body.append("question", params.question);
  body.append("namespace", params.namespace);
  body.append("strategy", params.strategy);
  body.append("use_hybrid", String(params.useHybrid));
  body.append("use_rerank", String(params.useRerank));

  const res = await fetch("/api/query", { method: "POST", body });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function ingestDocument(params: {
  file: File;
  namespace: string;
  strategy: string;
}): Promise<IngestResponse> {
  const body = new FormData();
  body.append("file", params.file);
  body.append("namespace", params.namespace);
  body.append("strategy", params.strategy);

  const res = await fetch("/api/ingest", { method: "POST", body });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchMetrics(): Promise<PlatformMetrics> {
  const res = await fetch("/api/metrics", { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function runEvaluation(params: {
  namespace: string;
  goldenSet: string;
  useLlmJudge: boolean;
  saveResults: boolean;
}): Promise<EvaluateResponse> {
  const body = new FormData();
  body.append("namespace", params.namespace);
  body.append("golden_set", params.goldenSet);
  body.append("use_llm_judge", String(params.useLlmJudge));
  body.append("save_results", String(params.saveResults));

  const res = await fetch("/api/evaluate", { method: "POST", body });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch("/api/health", { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
