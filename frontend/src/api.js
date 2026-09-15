export async function api(path, options = {}) {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

export function ago(iso) {
  if (!iso) return "no signal";
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (s < 8) return "just now";
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

export function prettyTime(iso) {
  if (!iso) return "—";
  return iso.replace("T", " ").slice(0, 19);
}

export function todayIST() {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
}

/** Browser used for DeskTrack — pages cannot see other desktop apps. */
export function detectBrowserApp() {
  const ua = navigator.userAgent || "";
  if (/Edg\//i.test(ua)) return "Edge";
  if (/OPR\/|Opera/i.test(ua)) return "Opera";
  if (/Brave/i.test(ua) || navigator.brave) return "Brave";
  if (/Chrome\//i.test(ua) && !/Edg\//i.test(ua)) return "Chrome";
  if (/Firefox\//i.test(ua)) return "Firefox";
  if (/Safari\//i.test(ua) && !/Chrome\//i.test(ua)) return "Safari";
  return "Browser";
}

export function detectDevice() {
  return /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent || "") ? "phone" : "laptop";
}
