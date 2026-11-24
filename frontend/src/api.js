const cookie = (name) => document.cookie.split("; ").find((r) => r.startsWith(name + "="))?.split("=")[1];

function message(data) {
  if (!data) return "Something went wrong. Try again.";
  if (data.detail) return data.detail;
  const first = Object.values(data)[0];
  return Array.isArray(first) ? first[0] : String(first);
}

// Netlify demo build (`npm run build:demo`): no server, see demoApi.js. In the normal build this is false
// and the demo code is dropped entirely.
export const DEMO = import.meta.env.MODE === "demo";

export async function api(path, { method = "GET", body } = {}) {
  if (DEMO) {
    const { demoRequest } = await import("./demoApi.js");
    await new Promise((resolve) => setTimeout(resolve, 150)); // feel like a network call
    return demoRequest(path, method, body);
  }
  const res = await fetch("/api" + path, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRFToken": cookie("csrftoken") || "" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw Object.assign(new Error(message(data)), { status: res.status });
  return data;
}
