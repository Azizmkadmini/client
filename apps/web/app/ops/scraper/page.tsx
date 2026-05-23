import { OpsLayout } from "@/components/ops/OpsLayout";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

function Col({ title, channel }: { title: string; channel: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-4 space-y-3">
      <h2 className="font-semibold text-white">{title}</h2>
      <p className="text-xs text-slate-500">Canal : {channel}</p>
      <label className="text-xs text-slate-400">Mode</label>
      <select className="w-full rounded-lg bg-slate-950 border border-slate-700 px-2 py-1.5 text-sm">
        <option>keyword</option>
        <option>hashtag</option>
      </select>
      <label className="text-xs text-slate-400">Requête</label>
      <Input placeholder="CEO SaaS Paris" />
      <label className="text-xs text-slate-400">Limite profils</label>
      <Input defaultValue="25" />
      <Button className="w-full text-sm">Lancer scraper</Button>
    </div>
  );
}

export default function OpsScraperPage() {
  return (
    <OpsLayout title="Scraper">
      <div className="grid md:grid-cols-3 gap-4">
        <Col title="LinkedIn" channel="linkedin" />
        <Col title="Instagram" channel="instagram" />
        <Col title="Web" channel="google" />
      </div>
      <div className="mt-6 rounded-xl border border-slate-800 overflow-hidden">
        <table className="w-full text-xs text-left">
          <thead className="bg-slate-900 text-slate-400">
            <tr>
              <th className="p-2">nom</th>
              <th className="p-2">email</th>
              <th className="p-2">whatsapp</th>
              <th className="p-2">entreprise</th>
            </tr>
          </thead>
          <tbody className="text-slate-300">
            <tr className="border-t border-slate-800">
              <td className="p-2">Marie D.</td>
              <td className="p-2">m@acme.io</td>
              <td className="p-2">—</td>
              <td className="p-2">Acme</td>
            </tr>
          </tbody>
        </table>
      </div>
    </OpsLayout>
  );
}
