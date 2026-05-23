import { getToken } from "./auth";



const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const ENV_KEY = process.env.NEXT_PUBLIC_API_KEY || "";



function headers(): HeadersInit {

  const h: Record<string, string> = { "Content-Type": "application/json" };

  const token = typeof window !== "undefined" ? getToken() : null;

  if (token) h["Authorization"] = `Bearer ${token}`;

  else if (ENV_KEY) h["X-API-Key"] = ENV_KEY;

  return h;

}



export async function apiGet<T>(path: string): Promise<T> {

  const res = await fetch(`${API}${path}`, { headers: headers(), cache: "no-store" });

  if (!res.ok) throw new Error(await res.text());

  return res.json() as Promise<T>;

}



export async function apiPost<T>(path: string, body: unknown): Promise<T> {

  const res = await fetch(`${API}${path}`, {

    method: "POST",

    headers: headers(),

    body: JSON.stringify(body),

  });

  if (!res.ok) throw new Error(await res.text());

  return res.json() as Promise<T>;

}

