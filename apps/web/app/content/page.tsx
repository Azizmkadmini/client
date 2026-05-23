"use client";

import { useEffect, useState } from "react";

import { DraftCard } from "@/components/DraftCard";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { EmptyState } from "@/components/ui/EmptyState";
import { Toast } from "@/components/ui/Toast";
import { apiGet, apiPost } from "@/lib/api";

type Draft = { id: string; body: string; hook?: string; status: string };

export default function ContentPage() {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [topic, setTopic] = useState("automation B2B");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [loading, setLoading] = useState(false);

  async function refresh() {
    const d = await apiGet<{ drafts: Draft[] }>("/api/v1/content/drafts");
    setDrafts(d.drafts);
  }

  useEffect(() => {
    refresh().catch((e) => setError(String(e)));
  }, []);

  async function generatePost() {
    setError("");
    setLoading(true);
    try {
      await apiPost("/api/v1/content/posts/generate", { topic, format: "expertise", language: "fr" });
      await refresh();
      setToast("Post généré");
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function publishDraft(draftId: string) {
    setError("");
    try {
      const post = await apiPost<{ post: { id: string } }>(`/api/v1/content/posts/from-draft/${draftId}`, {});
      await apiPost(`/api/v1/content/posts/${post.post.id}/publish`, { sync: true });
      await refresh();
      setToast("Publié sur LinkedIn");
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Content OS"
        description="Génération IA, validation et publication LinkedIn."
        actions={
          <a href="/content/calendar" className="text-sm text-emerald-400 hover:underline transition-colors">
            Calendrier →
          </a>
        }
      />
      <div className="flex gap-2">
        <Input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Sujet / topic" />
        <Button onClick={generatePost} disabled={loading}>
          {loading ? "Génération…" : "Générer post IA"}
        </Button>
      </div>
      <ErrorBanner message={error} onRetry={refresh} />
      {drafts.length === 0 ? (
        <EmptyState
          title="Aucun brouillon"
          description="Générez votre premier post avec un topic."
          action={<Button onClick={generatePost}>Générer</Button>}
        />
      ) : (
        <div className="space-y-3">
          {drafts.map((d) => (
            <DraftCard
              key={d.id}
              status={d.status}
              hook={d.hook}
              body={d.body}
              onApprove={async () => {
                await apiPost(`/api/v1/content/drafts/${d.id}/approve`, {});
                setToast("Approuvé");
                await refresh();
              }}
              onPublish={() => publishDraft(d.id)}
            />
          ))}
        </div>
      )}
      {toast ? <Toast message={toast} onDismiss={() => setToast("")} /> : null}
    </div>
  );
}
