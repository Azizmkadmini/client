import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

export function DraftCard({
  status,
  hook,
  body,
  onApprove,
  onReject,
  onPublish,
  onSchedule,
}: {
  status: string;
  hook?: string;
  body: string;
  onApprove?: () => void;
  onReject?: () => void;
  onPublish?: () => void;
  onSchedule?: () => void;
}) {
  return (
    <article className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Badge status={status} />
        <div className="flex flex-wrap gap-2">
          {onApprove ? (
            <Button variant="secondary" className="text-xs py-1.5 px-3" onClick={onApprove}>
              Approuver
            </Button>
          ) : null}
          {onReject ? (
            <Button variant="ghost" className="text-xs py-1.5 px-3" onClick={onReject}>
              Rejeter
            </Button>
          ) : null}
          {onSchedule ? (
            <Button variant="ghost" className="text-xs py-1.5 px-3" onClick={onSchedule}>
              Planifier
            </Button>
          ) : null}
          {onPublish ? (
            <Button className="text-xs py-1.5 px-3" onClick={onPublish}>
              Publier
            </Button>
          ) : null}
        </div>
      </div>
      {hook ? <p className="mt-2 text-sm font-medium text-slate-200">{hook}</p> : null}
      <p className="mt-2 text-sm text-slate-400 whitespace-pre-wrap line-clamp-6">{body}</p>
    </article>
  );
}
