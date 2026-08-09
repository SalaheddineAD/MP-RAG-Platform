export type QuerySource = {
  source: string;
  chunk_index: number;
};

export type QueryMetrics = {
  total_latency_ms: number;
  retrieval_latency_ms?: number;
  generation_latency_ms?: number;
  input_tokens?: number;
  output_tokens?: number;
  total_cost_usd?: number;
};

export type QueryResponse = {
  answer: string;
  sources: QuerySource[];
  retrieval_strategy?: string;
  chunking_strategy?: string;
  metrics: QueryMetrics;
};

export type IngestResponse = {
  status: string;
  filename: string;
  chunks_created: number;
  namespace: string;
  strategy: string;
  ingestion_time_ms: number;
};

export type PlatformMetrics = {
  total_queries?: number;
  total_cost_usd?: number;
  today_cost_usd?: number;
  daily_budget_usd?: number;
  budget_remaining_usd?: number;
  avg_latency_ms?: number;
  avg_cost_per_query?: number;
  p95_latency_ms?: number;
  budget_exceeded?: boolean;
};

export type DifficultyBreakdown = {
  faithfulness: number;
  answer_correctness: number;
  relevance: number;
  precision: number;
  count: number;
};

export type FailedQuery = {
  question: string;
  expected: string;
  generated: string;
  faithfulness: number;
  answer_correctness: number;
  relevance: number;
  retrieved_sources: string[];
  reason: string;
};

export type EvaluateResponse = {
  status: string;
  namespace: string;
  golden_set: string;
  saved_to: string | null;
  summary: {
    total_evaluated: number;
    avg_faithfulness: number;
    avg_answer_correctness: number;
    avg_answer_relevance: number;
    avg_context_precision: number;
    avg_latency_ms: number;
    p95_latency_ms: number;
    wall_clock_ms: number;
    avg_cost_per_query: number;
    total_cost_usd: number;
  };
  by_difficulty: Record<string, DifficultyBreakdown>;
  failed_queries: FailedQuery[];
  total_failures: number;
};

export type HealthResponse = {
  status: string;
  version: string;
};

export type ChunkStrategy = "recursive" | "semantic" | "agentic";
