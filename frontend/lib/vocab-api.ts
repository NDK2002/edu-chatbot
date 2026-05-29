import { getAccessToken } from "@/lib/supabase/client";

async function authHeaders(): Promise<Record<string, string>> {
  const token = await getAccessToken();
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

export async function syncVocabSave(word: {
  vi: string;
  tay_variants: string[];
  nung_variants: string[];
}): Promise<void> {
  await fetch("/api/history/vocab", {
    method: "POST",
    headers: await authHeaders(),
    body: JSON.stringify(word),
  }).catch(() => {});
}

export async function syncVocabDelete(vi: string): Promise<void> {
  await fetch("/api/history/vocab", {
    method: "DELETE",
    headers: await authHeaders(),
    body: JSON.stringify({ vi }),
  }).catch(() => {});
}

export async function syncVocabClearAll(): Promise<void> {
  await fetch("/api/history/vocab/all", {
    method: "DELETE",
    headers: await authHeaders(),
  }).catch(() => {});
}
