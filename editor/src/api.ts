async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || "请求失败");
  }
  return data as T;
}

export function parseTripText(text: string) {
  return postJson<import("./types").ParseResponse>("/api/parse", { text });
}

export function generateTrip(payload: import("./types").EditorPayload) {
  return postJson<import("./types").GenerateResponse>("/api/generate", payload);
}

export async function getDefaultText() {
  const response = await fetch("/api/default-text");
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || "默认数据读取失败");
  }
  return String(data.text || "");
}
