const API_URL = process.env.RAG_API_URL ?? "http://127.0.0.1:8000";

export function getApiUrl(path: string): string {
  const base = API_URL.replace(/\/$/, "");
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${base}${suffix}`;
}

export async function proxyFormPost(
  path: string,
  formData: FormData,
): Promise<Response> {
  return fetch(getApiUrl(path), {
    method: "POST",
    body: formData,
  });
}

export async function proxyJson(path: string): Promise<Response> {
  return fetch(getApiUrl(path), {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
}

export async function forwardJson(res: Response): Promise<Response> {
  const text = await res.text();
  return new Response(text, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
