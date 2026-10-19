export function Badge({ status }) {
  const label = status === "task" ? "on task" : status || "offline";
  return <span className={`badge ${status || ""}`}>{label}</span>;
}

