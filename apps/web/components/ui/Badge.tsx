type Status = "draft" | "scheduled" | "published" | "failed" | "dead" | "default";

const styles: Record<Status, string> = {
  draft: "bg-slate-800 text-slate-300",
  scheduled: "bg-sky-900/40 text-sky-300",
  published: "bg-emerald-900/40 text-emerald-300",
  failed: "bg-red-900/40 text-red-300",
  dead: "bg-red-950 text-red-400",
  default: "bg-slate-800 text-slate-400",
};

export function Badge({ status, label }: { status?: string; label?: string }) {
  const key = (status?.toLowerCase() || "default") as Status;
  const cls = styles[key] ?? styles.default;
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {label ?? status ?? "—"}
    </span>
  );
}
