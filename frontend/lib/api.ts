import { getAccessToken } from "@/lib/supabase/client";

const API_URL = "/api";

export class RateLimitError extends Error {
  resetInSeconds: number;
  reason: string;

  constructor(message: string, resetInSeconds: number, reason: string) {
    super(message);
    this.name = "RateLimitError";
    this.resetInSeconds = resetInSeconds;
    this.reason = reason;
  }
}

export interface VocabEntry {
  vi: string;
  tay?: string;
  nung?: string;
}

export interface ChatResponse {
  answer: string;
  steps?: string[];
  vocab?: VocabEntry[];
  source?: string;
  grade?: number;
}

export interface ChatMetadata {
  type: "metadata";
  source: string;
  intent?: string | null;
  vocab?: VocabEntry[] | null;
  steps?: string[] | null;
}

export interface ChatRequest {
  message: string;
  grade?: number;
  language?: string;
  mode: "student" | "teacher";
}

export interface LessonResponse {
  lesson_plan: string;
}

export async function sendChatMessage(
  message: string,
  mode: "student" | "teacher" = "student"
): Promise<ChatResponse> {
  const res = await fetch(`${API_URL}/v2/chat/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, mode }),
  });
  if (!res.ok) {
    if (res.status === 429) {
      const data = await res.json();
      throw new RateLimitError(data.message, data.reset_in_seconds, data.reason);
    }
    if (res.status === 503) {
      throw new Error("AI_UNAVAILABLE");
    }
    throw new Error(`Lỗi máy chủ: ${res.status}`);
  }
  return res.json();
}

export async function streamChat(
  payload: ChatRequest,
  onChunk: (text: string) => void,
  onMetadata: (metadata: ChatMetadata) => void,
  onDone: () => void,
  onError: (error: string) => void,
): Promise<void> {
  const token = await getAccessToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch("/api/v2/chat/", {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });
  } catch {
    onError("Không thể kết nối tới máy chủ AI. Vui lòng thử lại sau.");
    return;
  }

  if (!response.ok) {
    if (response.status === 429) {
      const data = await response.json();
      throw new RateLimitError(data.message, data.reset_in_seconds, data.reason);
    }
    if (response.status === 503) {
      onError("AI_UNAVAILABLE");
      return;
    }
    onError(`Lỗi máy chủ: ${response.status}`);
    return;
  }

  if (!response.body) {
    onError("Không nhận được phản hồi từ máy chủ.");
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const data = JSON.parse(line.slice(6));
        if (data.type === "metadata") onMetadata(data as ChatMetadata);
        else if (data.type === "chunk") onChunk(data.text as string);
        else if (data.type === "done") onDone();
        else if (data.type === "error") onError((data.message as string) ?? "INTERNAL_ERROR");
      } catch {
        // ignore malformed SSE JSON
      }
    }
  }
}

export async function generateLesson(
  topic: string,
  grade: number,
  subject: string
): Promise<LessonResponse> {
  const res = await fetch(`${API_URL}/teacher/lesson`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, grade, subject }),
  });
  if (!res.ok) throw new Error(`Lỗi máy chủ: ${res.status}`);
  return res.json();
}
