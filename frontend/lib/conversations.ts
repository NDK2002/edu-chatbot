import { getAccessToken } from "@/lib/supabase/client";

export interface Conversation {
  id: string;
  title: string;
  mode: string;
  is_compacted: boolean;
  message_count: number;
  last_message_at: string;
  created_at: string;
}

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  query_type?: string;
  source?: string;
  is_compacted: boolean;
  created_at: string;
}

export interface ConversationMessagesResponse {
  compact_summary: string | null;
  messages: ConversationMessage[];
}

async function authHeaders(): Promise<Record<string, string>> {
  const token = await getAccessToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

export async function listConversations(): Promise<Conversation[]> {
  const res = await fetch("/api/conversations", { headers: await authHeaders() });
  if (!res.ok) return [];
  return res.json();
}

export async function createConversation(mode: string = "student"): Promise<Conversation> {
  const res = await fetch("/api/conversations", {
    method: "POST",
    headers: await authHeaders(),
    body: JSON.stringify({ mode }),
  });
  if (!res.ok) throw new Error("Không thể tạo cuộc trò chuyện");
  return res.json();
}

export async function deleteConversation(id: string): Promise<void> {
  await fetch(`/api/conversations/${id}`, {
    method: "DELETE",
    headers: await authHeaders(),
  });
}

export async function getConversationMessages(id: string): Promise<ConversationMessagesResponse | null> {
  const res = await fetch(`/api/conversations/${id}/messages`, { headers: await authHeaders() });
  if (res.status === 404) return null;
  if (!res.ok) return null;
  return res.json();
}

export async function updateConversationTitle(id: string, title: string): Promise<void> {
  await fetch(`/api/conversations/${id}/title`, {
    method: "PATCH",
    headers: await authHeaders(),
    body: JSON.stringify({ title }),
  });
}
