function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function badge(status) {
  return `<span class="badge ${esc(status)}">${esc(status)}</span>`;
}

function ago(iso) {
  if (!iso) return "no signal";
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (s < 8) return "just now";
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

function prettyTime(iso) {
  if (!iso) return "—";
  return iso.replace("T", " ").slice(0, 19);
}
