import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";

export default function AdminGdprPage() {
  return (
    <div className="space-y-6 max-w-2xl">
      <PageHeader title="GDPR" description="Export et suppression des données tenant." />
      <div className="rounded-xl border border-slate-800 p-6 space-y-4">
        <p className="text-sm text-slate-400">Export JSON des données personnelles (enterprise API).</p>
        <Button variant="secondary">Exporter mes données</Button>
      </div>
      <div className="rounded-xl border border-red-900/50 bg-red-950/20 p-6 space-y-4">
        <p className="text-sm text-red-300">Suppression définitive du tenant — irréversible.</p>
        <Button variant="danger">Demander suppression</Button>
      </div>
    </div>
  );
}
