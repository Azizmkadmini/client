import { OpsLayout } from "@/components/ops/OpsLayout";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export default function OpsCompliancePage() {
  return (
    <OpsLayout title="Conformité">
      <table className="w-full text-xs mb-6 rounded-xl border border-slate-800">
        <thead className="bg-slate-900 text-slate-400">
          <tr>
            <th className="p-2 text-left">identifier</th>
            <th className="p-2">reason</th>
            <th className="p-2">created_at</th>
          </tr>
        </thead>
        <tbody className="text-slate-300">
          <tr className="border-t border-slate-800">
            <td className="p-2">user@example.com</td>
            <td className="p-2">user_request</td>
            <td className="p-2">2026-05-20</td>
          </tr>
        </tbody>
      </table>
      <div className="flex gap-2 max-w-md">
        <Input placeholder="email ou identifiant" />
        <Button>Opt-out</Button>
      </div>
    </OpsLayout>
  );
}
