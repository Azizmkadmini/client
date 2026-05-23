import { OpsLayout } from "@/components/ops/OpsLayout";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/Input";

export default function OpsContentPage() {
  return (
    <OpsLayout title="Content OS">
      <div className="flex gap-2 border-b border-slate-800 mb-4 text-sm">
        {["Génération", "Calendrier", "Publication", "Optimisation"].map((t, i) => (
          <span key={t} className={`pb-2 px-2 ${i === 0 ? "border-b-2 border-indigo-500 text-white" : "text-slate-500"}`}>
            {t}
          </span>
        ))}
      </div>
      <div className="space-y-4 max-w-2xl">
        <Input placeholder="Sujet / topic" defaultValue="automation B2B LinkedIn" />
        <Button>Générer hooks</Button>
        <ul className="text-sm text-slate-400 list-disc pl-5 space-y-1">
          <li>3 leviers pour scaler votre outreach en 2026</li>
          <li>Pourquoi 80% des équipes échouent sur LinkedIn</li>
        </ul>
        <Button variant="secondary">Générer post complet</Button>
        <Textarea rows={6} defaultValue="Voici comment structurer une machine à contenu B2B..." />
      </div>
    </OpsLayout>
  );
}
