const cookie = (name) => document.cookie.split("; ").find((r) => r.startsWith(name + "="))?.split("=")[1];

function message(data) {
  if (!data) return "Something went wrong. Try again.";
  if (data.detail) return data.detail;
  const first = Object.values(data)[0];
  return Array.isArray(first) ? first[0] : String(first);
}

export async function api(path, { method = "GET", body } = {}) {
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
