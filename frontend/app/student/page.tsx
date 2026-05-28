"use client";

import { useState, useRef, useEffect, useSyncExternalStore } from "react";
import Image from "next/image";
import AppShell from "@/components/AppShell";
import ChatBubble from "@/components/ChatBubble";
import { streamChat, ChatResponse, RateLimitError } from "@/lib/api";

interface Message {
  id: number;
  role: "user" | "bot";
  content: string;
  steps?: string[];
  vocab?: ChatResponse["vocab"];
  source?: string;
  grade?: number;
  loading?: boolean;
  animate?: boolean;
  streaming?: boolean;
}

const CHAT_STORAGE_KEY = "edu-chatbot-student-messages";
const DEFAULT_MESSAGES: Message[] = [
  {
    id: 0,
    role: "bot",
    content:
      "Xin chào! Mình là trợ lý học tập của em.\nMình có thể giúp em:\n- Giải bài Toán từng bước\n- Giải thích từ khó trong đề bài\n- Tra từ tiếng Tày, tiếng Nùng\n\nEm muốn hỏi gì hôm nay?",
  },
];
let currentMessagesSnapshot: Message[] | null = null;

function loadStoredMessages(): Message[] {
  if (typeof window === "undefined") return DEFAULT_MESSAGES;

  try {
    const raw = window.localStorage.getItem(CHAT_STORAGE_KEY);
    if (!raw) return DEFAULT_MESSAGES;

    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length === 0) return DEFAULT_MESSAGES;

    return parsed
      .filter((msg): msg is Message => Boolean(msg && typeof msg.content === "string"))
      .map((msg) => ({
        ...msg,
        loading: false,
        animate: false,
      }));
  } catch {
    return DEFAULT_MESSAGES;
  }
}

function getMessagesSnapshot(): Message[] {
  if (currentMessagesSnapshot) return currentMessagesSnapshot;
  currentMessagesSnapshot = loadStoredMessages();
  return currentMessagesSnapshot;
}

const messageStoreListeners = new Set<() => void>();

function emitStoredMessagesChange() {
  messageStoreListeners.forEach((listener) => listener());
}

function subscribeToMessages(listener: () => void) {
  messageStoreListeners.add(listener);

  const handleStorage = (event: StorageEvent) => {
    if (event.key === CHAT_STORAGE_KEY) {
      currentMessagesSnapshot = loadStoredMessages();
      listener();
    }
  };

  window.addEventListener("storage", handleStorage);

  return () => {
    messageStoreListeners.delete(listener);
    window.removeEventListener("storage", handleStorage);
  };
}

function saveMessages(messages: Message[]) {
  currentMessagesSnapshot = messages;
  if (typeof window !== "undefined") {
    const persistedMessages = messages.filter((msg) => !msg.loading && !msg.streaming);
    window.localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(persistedMessages));
  }
  emitStoredMessagesChange();
}

function updateMessages(updater: (messages: Message[]) => Message[]) {
  const nextMessages = updater(getMessagesSnapshot());
  saveMessages(nextMessages);
}

const SUGGESTIONS = [
  "Chu vi hình vuông là gì?",
  "Tính 24 × 6 = ?",
  "Phân số là gì?",
  "Diện tích hình chữ nhật tính thế nào?",
];

export default function StudentPage() {
  const messages = useSyncExternalStore(
    subscribeToMessages,
    getMessagesSnapshot,
    () => DEFAULT_MESSAGES
  );
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [cooldownSeconds, setCooldownSeconds] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const nextId = useRef(Math.max(0, ...messages.map((msg) => msg.id)) + 1);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    nextId.current = Math.max(0, ...messages.map((msg) => msg.id)) + 1;
  }, [messages]);

  // Countdown timer for rate-limit cooldown
  useEffect(() => {
    if (cooldownSeconds <= 0) return;
    const timer = setTimeout(() => setCooldownSeconds((s) => Math.max(0, s - 1)), 1000);
    return () => clearTimeout(timer);
  }, [cooldownSeconds]);

  async function handleSend(text: string) {
    const trimmed = text.trim();
    if (!trimmed || isSending) return;

    const userMsg: Message = {
      id: nextId.current++,
      role: "user",
      content: trimmed,
    };
    const botId = nextId.current++;
    const loadingMsg: Message = {
      id: botId,
      role: "bot",
      content: "",
      loading: true,
    };

    updateMessages((prev) => [...prev, userMsg, loadingMsg]);
    setInput("");
    setIsSending(true);

    try {
      await streamChat(
        { message: trimmed, mode: "student" },
        // onChunk — append text, switch from loading to streaming on first chunk
        (chunk) => {
          updateMessages((prev) =>
            prev.map((m) =>
              m.id === botId
                ? { ...m, loading: false, streaming: true, content: m.content + chunk }
                : m
            )
          );
        },
        // onMetadata — store source/vocab/steps from server before chunks arrive
        (meta) => {
          updateMessages((prev) =>
            prev.map((m) =>
              m.id === botId
                ? {
                    ...m,
                    loading: false,
                    streaming: true,
                    source: meta.source,
                    vocab: meta.vocab ?? undefined,
                    steps: meta.steps ?? undefined,
                  }
                : m
            )
          );
        },
        // onDone — mark streaming complete, vocab/steps now visible
        () => {
          updateMessages((prev) =>
            prev.map((m) =>
              m.id === botId ? { ...m, streaming: false } : m
            )
          );
        },
        // onError
        (error) => {
          const botContent =
            error === "AI_UNAVAILABLE"
              ? "Hệ thống đang bận, vui lòng thử lại sau vài phút."
              : "Đã có lỗi xảy ra. Vui lòng thử lại sau.";
          updateMessages((prev) =>
            prev.map((m) =>
              m.id === botId
                ? { ...m, loading: false, streaming: false, content: botContent }
                : m
            )
          );
        },
      );
    } catch (err) {
      if (err instanceof RateLimitError) {
        setCooldownSeconds(err.resetInSeconds);
        updateMessages((prev) =>
          prev.map((m) =>
            m.id === botId
              ? { ...m, loading: false, streaming: false, content: err.message }
              : m
          )
        );
      } else {
        updateMessages((prev) =>
          prev.map((m) =>
            m.id === botId
              ? { ...m, loading: false, streaming: false, content: "Đã có lỗi xảy ra. Vui lòng thử lại sau." }
              : m
          )
        );
      }
    } finally {
      setIsSending(false);
      inputRef.current?.focus();
    }
  }

  function handleSubmit(e: React.SyntheticEvent) {
    e.preventDefault();
    handleSend(input);
  }

  return (
    <AppShell>
    <div className="flex flex-col h-full bg-gradient-to-b from-sky-50 to-indigo-50">
      {/* Header */}
      <header className="flex items-center gap-2 px-4 py-3 bg-white border-b border-sky-100 shadow-sm">
        <div className="md:hidden w-8 h-8 rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 flex items-center justify-center shadow overflow-hidden">
          <Image src="/student-icon.png" alt="Học sinh" width={22} height={22} loading="eager" />
        </div>
        <div>
          <h1 className="font-bold text-sky-800 text-sm leading-tight">Chat học sinh</h1>
          <p className="text-xs text-sky-500">Việt–Tày/Nùng · Lớp 1–5</p>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.map((msg) => (
          <ChatBubble
            key={msg.id}
            role={msg.role}
            content={msg.content}
            steps={msg.steps}
            vocab={msg.vocab}
            source={msg.source}
            grade={msg.grade}
            loading={msg.loading}
            animate={msg.animate}
            streaming={msg.streaming}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Suggestions */}
      {messages.length <= 1 && (
        <div className="px-4 pb-2 flex flex-wrap gap-2 justify-center">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => handleSend(s)}
              className="text-sm px-3 py-1.5 bg-white border border-sky-200 text-sky-700 rounded-full hover:bg-sky-50 hover:border-sky-400 transition-colors shadow-sm"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Rate-limit cooldown banner */}
      {cooldownSeconds > 0 && (
        <div className="px-4 pb-2">
          <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-2 text-sm text-amber-700 text-center">
            Vui lòng thử lại sau{" "}
            {cooldownSeconds < 3600
              ? `${cooldownSeconds} giây`
              : `${Math.ceil(cooldownSeconds / 60)} phút`}
          </div>
        </div>
      )}

      {/* Input */}
      <form
        onSubmit={handleSubmit}
        className="px-4 py-3 bg-white border-t border-gray-100 flex items-center gap-2"
      >
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Em hỏi bài ở đây nhé... ✏️"
          className="flex-1 px-4 py-3 rounded-2xl border border-gray-200 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-sky-300 focus:border-sky-300 text-sm text-gray-800 placeholder:text-gray-400"
          disabled={isSending || cooldownSeconds > 0}
          autoFocus
        />
        <button
          type="submit"
          disabled={!input.trim() || isSending || cooldownSeconds > 0}
          className="w-11 h-11 flex items-center justify-center rounded-full bg-sky-500 text-white shadow hover:bg-sky-600 active:scale-95 transition-all disabled:opacity-40 disabled:cursor-not-allowed text-lg"
          aria-label="Gửi"
        >
          {isSending ? (
            <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
          ) : (
            "➤"
          )}
        </button>
      </form>
    </div>
    </AppShell>
  );
}
