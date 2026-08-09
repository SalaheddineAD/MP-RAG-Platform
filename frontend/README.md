# MP RAG Frontend

Next.js console for the Manufacturing RAG Platform: query, ingest, metrics, and golden-set evaluation.

## Setup

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The API must be running on port 8000 (or set `RAG_API_URL` in `.env.local`).

## Pages

| Route | Purpose |
| --- | --- |
| `/` | Query console with citations and per-query telemetry |
| `/ingest` | Document upload into a namespace |
| `/metrics` | Live platform cost and latency |
| `/evaluate` | Golden-set evaluation runner |

Browser calls go through Next.js route handlers under `/api/*`, which proxy to FastAPI.
