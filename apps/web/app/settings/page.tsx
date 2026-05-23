"use client";

import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Toast } from "@/components/ui/Toast";
import { apiGet } from "@/lib/api";
import { getToken } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export default function SettingsPage() {
  const [oauth, setOauth] = useState<{ connected?: boolean; configured?: boolean } | null>(null);
  const [keys, setKeys] = useState<{ id: string; name: string; prefix: string }[]>([]);
  const [modalKey, setModalKey] = useState<string | null>(null);
  const [toast, setToast] = useState("");

  useEffect(() => {
    apiGet<{ connected?: boolean; configured?: boolean }>("/api/v1/oauth/linkedin/status").then(setOauth);
    apiGet<{ id: string; name: string; key_prefix: string }[]>("/api/v1/billing/api-keys")
      .then((rows) =>
        setKeys(
          (rows as { id: string; name: string; key_prefix: string }[]).map((r) => ({
            id: r.id,
            name: r.name,
            prefix: r.key_prefix,
          }))
        )
      )
      .catch(() => setKeys([]));
  }, []);

  async function connectLinkedIn() {
    const token = getToken();
    const res = await fetch(`${API}/api/v1/oauth/linkedin/authorize`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    const data = (await res.json()) as { authorization_url: string };
    window.location.href = data.authorization_url;
  }

  async function createApiKey() {
    const res = await fetch(`${API}/api/v1/billing/api-keys?name=web`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
      },
    });
    const data = (await res.json()) as { api_key?: string };
    if (data.api_key) {
      setModalKey(data.api_key);
      setToast("Clé API créée");
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader title="Paramètres" description="OAuth LinkedIn, clés API, intégrations." />
      <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 space-y-4">
        <h2 className="font-semibold text-white">LinkedIn OAuth</h2>
        <p className="text-sm text-slate-400">
          {oauth?.connected ? "● Connecté" : oauth?.configured ? "○ Non connecté" : "Client ID non configuré"}
        </p>
        <Button onClick={connectLinkedIn}>Connecter LinkedIn</Button>
      </section>
      <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 space-y-4">
        <h2 className="font-semibold text-white">Clés API</h2>
        <ul className="text-sm text-slate-400 space-y-1">
          {keys.map((k) => (
            <li key={k.id}>
              {k.name} — <span className="font-mono">{k.prefix}…</span>
            </li>
          ))}
        </ul>
        <Button variant="secondary" onClick={createApiKey}>
          Nouvelle clé API
        </Button>
      </section>
      <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 space-y-2 text-sm">
        <h2 className="font-semibold text-white">Admin</h2>
        <p>
          <a href="/admin/audit" className="text-emerald-400 hover:underline">
            Audit log
          </a>
          {" · "}
          <a href="/admin/feature-flags" className="text-emerald-400 hover:underline">
            Feature flags
          </a>
          {" · "}
          <a href="/admin/gdpr" className="text-emerald-400 hover:underline">
            GDPR
          </a>
          {" · "}
          <a href="/admin/sso" className="text-emerald-400 hover:underline">
            SSO
          </a>
        </p>
      </section>
      <Modal
        open={!!modalKey}
        title="Clé API — copiez maintenant"
        onClose={() => setModalKey(null)}
        actions={
          <Button
            onClick={() => {
              if (modalKey) navigator.clipboard.writeText(modalKey);
              setToast("Copié");
              setModalKey(null);
            }}
          >
            Copier et fermer
          </Button>
        }
      >
        <code className="block break-all rounded bg-slate-950 p-3 text-emerald-400 text-xs">{modalKey}</code>
        <p className="mt-2 text-xs text-slate-500">Affichée une seule fois.</p>
      </Modal>
      {toast ? <Toast message={toast} onDismiss={() => setToast("")} /> : null}
    </div>
  );
}
