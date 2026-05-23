import { PageHeader } from "@/components/ui/PageHeader";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";

export default function AdminSsoPage() {
  return (
    <div className="space-y-6 max-w-lg">
      <PageHeader title="SSO / OIDC" description="Configuration enterprise (hooks)." />
      <label className="block text-xs text-slate-500">Issuer</label>
      <Input placeholder="https://idp.example.com" />
      <label className="block text-xs text-slate-500">Client ID</label>
      <Input placeholder="oidc-client-id" />
      <Button>Enregistrer</Button>
    </div>
  );
}
