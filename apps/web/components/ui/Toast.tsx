"use client";

import { useEffect } from "react";

export function Toast({
  message,
  variant = "success",
  onDismiss,
}: {
  message: string;
  variant?: "success" | "error" | "info";
  onDismiss?: () => void;
}) {
  useEffect(() => {
    if (!onDismiss) return;
    const t = setTimeout(onDismiss, 3000);
    return () => clearTimeout(t);
  }, [message, onDismiss]);

  const styles =
    variant === "error"
      ? "border-red-800 bg-red-950/80 text-red-200"
      : variant === "info"
        ? "border-sky-800 bg-sky-950/80 text-sky-200"
        : "border-emerald-800 bg-emerald-950/80 text-emerald-200";
  return (
    <div
      className={`fixed bottom-6 right-6 z-50 rounded-lg border px-4 py-3 text-sm shadow-lg animate-slide-up ${styles}`}
      role="status"
    >
      {message}
    </div>
  );
}
