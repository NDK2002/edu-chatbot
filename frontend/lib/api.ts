const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
