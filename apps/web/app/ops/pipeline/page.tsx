import { OpsLayout } from "@/components/ops/OpsLayout";
import { Button } from "@/components/ui/Button";

export default function OpsPipelinePage() {
  return (
    <OpsLayout title="Pipeline">
      <div className="grid md:grid-cols-2 gap-6 max-w-3xl">
        <div className="space-y-3 text-sm">
          <label className="text-slate-400">Source</label>
          <select className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2">
            <option>csv</option>
            <option>sqlite</option>
            <option>mongo</option>
          </select>
          <label className="flex items-center gap-2 text-slate-400">
            <input type="checkbox" defaultChecked /> Retry failed
          </label>
          <label className="flex items-center gap-2 text-slate-400">
            <input type="checkbox" defaultChecked /> Run scraper step
          </label>
          <Button>Pipeline complet</Button>
          <Button variant="secondary">Connector + ingest</Button>
        </div>
        <div className="space-y-2">
          <p className="text-sm text-slate-400">Outreach par canal</p>
          {["linkedin", "instagram", "whatsapp", "email"].map((ch) => (
            <div key={ch} className="flex items-center justify-between rounded-lg border border-slate-800 px-3 py-2">
              <span className="text-sm capitalize">{ch}</span>
              <Button className="text-xs py-1 px-2">Envoyer</Button>
            </div>
          ))}
        </div>
      </div>
    </OpsLayout>
  );
}
