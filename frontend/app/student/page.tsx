"use client";

import { useState, useRef, useEffect, FormEvent } from "react";
import ChatBubble from "@/components/ChatBubble";
import ModeToggle from "@/components/ModeToggle";
import { sendChatMessage, ChatResponse } from "@/lib/api";

interface Message {
  id: number;
  role: "user" | "bot";
  content: string;
  steps?: string[];
  vocab?: ChatResponse["vocab"];
  source?: string;
  grade?: number;
  loading?: boolean;
}

const SUGGESTIONS = [
  "Chu vi hình vuông là gì?",
  "Tính 24 × 6 = ?",
  "Phân số là gì?",
  "Diện tích hình chữ nhật tính thế nào?",
];

export default function StudentPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 0,
      role: "bot",
      content:
        "Xin chào! 👋 Mình là trợ lý học Toán của em. Em có thể hỏi mình về bất kỳ bài Toán nào từ lớp 1 đến lớp 5 nhé!",
    },
  ]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const nextId = useRef(1);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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

    setMessages((prev) => [...prev, userMsg, loadingMsg]);
    setInput("");
    setIsSending(true);

    try {
      const res = await sendChatMessage(trimmed, "student");
      setMessages((prev) =>
        prev.map((m) =>
          m.id === botId
            ? {
                ...m,
                loading: false,
                content: res.answer,
                steps: res.steps,
                vocab: res.vocab,
                source: res.source,
                grade: res.grade,
              }
            : m
        )
      );
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === botId
            ? {
                ...m,
                loading: false,
                content: `Có lỗi xảy ra: ${(err as Error).message}. Vui lòng thử lại.`,
              }
            : m
        )
      );
    } finally {
      setIsSending(false);
      inputRef.current?.focus();
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    handleSend(input);
  }

  return (
    <div className="flex flex-col h-screen bg-gradient-to-b from-sky-50 to-indigo-50">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 bg-white border-b border-sky-100 shadow-sm sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 flex items-center justify-center text-xl shadow">
            🎒
          </div>
          <div>
            <h1 className="font-bold text-sky-800 text-base leading-tight">
              Chatbot Giáo dục
            </h1>
            <p className="text-xs text-sky-500">Việt–Tày/Nùng · Lớp 1–5</p>
          </div>
        </div>
        <ModeToggle />
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
            // source={msg.source}
            // grade={msg.grade}
            loading={msg.loading}
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
          disabled={isSending}
          autoFocus
        />
        <button
          type="submit"
          disabled={!input.trim() || isSending}
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
  );
}
