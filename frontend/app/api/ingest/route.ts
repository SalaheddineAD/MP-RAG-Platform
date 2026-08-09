import { forwardJson, proxyFormPost } from "@/lib/server-api";

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const upstream = await proxyFormPost("/ingest", formData);
    return forwardJson(upstream);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to reach RAG API";
    return Response.json({ error: message }, { status: 502 });
  }
}
