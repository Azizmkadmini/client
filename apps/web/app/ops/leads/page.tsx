import { OpsLayout } from "@/components/ops/OpsLayout";
import { Button } from "@/components/ui/Button";

export default function OpsLeadsPage() {
  return (
    <OpsLayout title="Leads">
      <div className="flex gap-2 mb-4">
        <select className="rounded-lg bg-slate-950 border border-slate-700 px-2 py-1 text-sm">
          <option>Tous statuts</option>
        </select>
        <select className="rounded-lg bg-slate-950 border border-slate-700 px-2 py-1 text-sm">
          <option>Tous canaux</option>
        </select>
        <Button variant="secondary" className="text-xs">
          Importer CSV
        </Button>
      </div>
      <div className="rounded-xl border border-slate-800 overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-slate-900 text-slate-400">
            <tr>
              <th className="p-2 text-left">name</th>
              <th className="p-2">email</th>
              <th className="p-2">status</th>
              <th className="p-2">channel</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-slate-800 text-slate-300">
              <td className="p-2">Jean P.</td>
              <td className="p-2">j@corp.fr</td>
              <td className="p-2">new</td>
              <td className="p-2">linkedin</td>
            </tr>
          </tbody>
        </table>
      </div>
    </OpsLayout>
  );
}
