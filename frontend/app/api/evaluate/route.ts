import { forwardJson, proxyFormPost } from "@/lib/server-api";

// Golden-set evaluation can take several minutes.
export const maxDuration = 300;

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const upstream = await proxyFormPost("/evaluate", formData);
    return forwardJson(upstream);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to reach RAG API";
    return Response.json({ error: message }, { status: 502 });
  }
}
