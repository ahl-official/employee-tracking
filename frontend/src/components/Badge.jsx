export function Badge({ status }) {
  return <span className={`badge ${status || ""}`}>{status || "offline"}</span>;
}
