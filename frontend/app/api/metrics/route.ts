import { forwardJson, proxyJson } from "@/lib/server-api";

export async function GET() {
  try {
    const upstream = await proxyJson("/metrics");
    return forwardJson(upstream);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to reach RAG API";
    return Response.json({ error: message }, { status: 502 });
  }
}
