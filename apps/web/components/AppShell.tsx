"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { clearToken, getToken } from "@/lib/auth";
import { Button } from "@/components/ui/Button";

const NAV = [
  { href: "/", label: "Accueil" },
  { href: "/acquisition", label: "Acquisition" },
  { href: "/content", label: "Content OS" },
  { href: "/content/calendar", label: "Calendrier" },
  { href: "/analytics", label: "Analytics" },
  { href: "/campaigns", label: "Campagnes" },
  { href: "/accounts", label: "Comptes" },
  { href: "/billing", label: "Billing" },
  { href: "/settings", label: "Paramètres" },
] as const;

const PUBLIC = new Set(["/login"]);
const PUBLIC_PREFIX = ["/ops", "/admin"];

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2.5 shrink-0 group">
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-600/20 border border-emerald-600/40 text-emerald-400 font-bold text-sm group-hover:bg-emerald-600/30 transition-colors">
        A
      </span>
      <span className="font-semibold text-white hidden sm:block">AI Acquisition OS</span>
    </Link>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [loggedIn, setLoggedIn] = useState(false);

  useEffect(() => {
    setLoggedIn(!!getToken());
  }, [pathname]);

  useEffect(() => {
    if (PUBLIC.has(pathname) || PUBLIC_PREFIX.some((p) => pathname.startsWith(p))) return;
    if (!getToken()) {
      router.replace("/login");
    }
  }, [pathname, router]);

  function logout() {
    clearToken();
    setLoggedIn(false);
    router.push("/login");
  }

  const isLogin = pathname === "/login";

  return (
    <div className="min-h-screen flex flex-col">
      {!isLogin ? (
        <header className="sticky top-0 z-40 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-6 py-3.5">
            <Logo />
            <nav className="flex flex-wrap gap-1 text-sm">
              {NAV.map(({ href, label }) => {
                const active = pathname === href || (href !== "/" && pathname.startsWith(href));
                return (
                  <Link
                    key={href}
                    href={href}
                    className={
                      active
                        ? "rounded-md bg-emerald-950/80 px-3 py-1.5 text-emerald-400 font-medium"
                        : "rounded-md px-3 py-1.5 text-slate-400 hover:bg-slate-800/80 hover:text-slate-200"
                    }
                  >
                    {label}
                  </Link>
                );
              })}
            </nav>
            <div className="ml-auto flex items-center gap-2">
              {loggedIn ? (
                <Button variant="ghost" className="text-xs py-1.5 px-3" onClick={logout}>
                  Déconnexion
                </Button>
              ) : (
                <Link
                  href="/login"
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 transition-colors"
                >
                  Login
                </Link>
              )}
            </div>
          </div>
        </header>
      ) : null}
      <main className={isLogin ? "flex-1" : "mx-auto w-full max-w-6xl flex-1 p-6 animate-fade-in"}>
        {children}
      </main>
    </div>
  );
}
