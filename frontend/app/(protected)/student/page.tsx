"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import ChatBubble from "@/components/ChatBubble";
import { streamChat, ChatResponse, RateLimitError } from "@/lib/api";
import { useConversation } from "@/lib/ConversationContext";
import { getConversationMessages } from "@/lib/conversations";

interface Message {
  id: number;
  role: "user" | "bot";
  content: string;
  steps?: string[];
  vocab?: ChatResponse["vocab"];
  source?: string;
  grade?: number;
  loading?: boolean;
  streaming?: boolean;
}

const DEFAULT_MESSAGES: Message[] = [
  {
    id: 0,
    role: "bot",
    content:
      "Xin chào! Mình là trợ lý học tập của em.\nMình có thể giúp em:\n- Giải bài Toán từng bước\n- Giải thích từ khó trong đề bài\n- Tra từ tiếng Tày, tiếng Nùng\n\nEm muốn hỏi gì hôm nay?",
  },
];

const SUGGESTIONS = [
  "Chu vi hình vuông là gì?",
  "Tính 24 × 6 = ?",
  "Phân số là gì?",
  "Diện tích hình chữ nhật tính thế nào?",
];

export default function StudentPage() {
  const {
    activeConversationId,
    setActiveConversationId,
    refreshConversations,
    toggleSidebar,
  } = useConversation();

  const [messages, setMessages] = useState<Message[]>(DEFAULT_MESSAGES);
  const [compactSummary, setCompactSummary] = useState<string | null>(null);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [cooldownSeconds, setCooldownSeconds] = useState(0);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const nextIdRef = useRef(1);

  // Tracks live conversation id during streaming (may differ from context briefly)
  const liveConvIdRef = useRef<string | null>(null);
  // Prevents reload after WE update activeConversationId post-stream
  const suppressReloadRef = useRef(false);

  // Load messages when active conversation changes
  useEffect(() => {
    liveConvIdRef.current = activeConversationId;

    if (suppressReloadRef.current) {
      suppressReloadRef.current = false;
      return;
    }

    if (activeConversationId === null) {
      setMessages(DEFAULT_MESSAGES);
      setCompactSummary(null);
      nextIdRef.current = 1;
      return;
    }

    setIsLoadingMessages(true);
    getConversationMessages(activeConversationId)
      .then((data) => {
        if (!data) {
          setMessages(DEFAULT_MESSAGES);
          setCompactSummary(null);
          return;
        }
        setCompactSummary(data.compact_summary);
        if (data.messages.length === 0) {
          setMessages(DEFAULT_MESSAGES);
          return;
        }
        const converted: Message[] = data.messages.map((m, i) => ({
          id: i,
          role: m.role === "user" ? "user" : "bot",
          content: m.content,
          source: m.source ?? undefined,
        }));
        nextIdRef.current = converted.length;
        setMessages(converted);
      })
      .catch(() => {
        setMessages(DEFAULT_MESSAGES);
        setCompactSummary(null);
      })
      .finally(() => setIsLoadingMessages(false));
  }, [activeConversationId]);

  // Scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Cooldown countdown
  useEffect(() => {
    if (cooldownSeconds <= 0) return;
    const timer = setTimeout(() => setCooldownSeconds((s) => Math.max(0, s - 1)), 1000);
    return () => clearTimeout(timer);
  }, [cooldownSeconds]);

  const handleSend = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isSending) return;

      const userMsgId = nextIdRef.current++;
      const botMsgId = nextIdRef.current++;

      setMessages((prev) => [
        ...prev,
        { id: userMsgId, role: "user", content: trimmed },
        { id: botMsgId, role: "bot", content: "", loading: true },
      ]);
      setInput("");
      setIsSending(true);

      try {
        await streamChat(
          {
            message: trimmed,
            conversation_id: liveConvIdRef.current,
            mode: "student",
          },
          (chunk) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === botMsgId
                  ? { ...m, loading: false, streaming: true, content: m.content + chunk }
                  : m,
              ),
            );
          },
          (meta) => {
            // Capture new conversation_id if backend created one
            if (meta.conversation_id) {
              liveConvIdRef.current = meta.conversation_id;
            }
            setMessages((prev) =>
              prev.map((m) =>
                m.id === botMsgId
                  ? {
                      ...m,
                      loading: false,
                      streaming: true,
                      source: meta.source,
                      vocab: meta.vocab ?? undefined,
                      steps: meta.steps ?? undefined,
                    }
                  : m,
              ),
            );
          },
          () => {
            setMessages((prev) =>
              prev.map((m) => (m.id === botMsgId ? { ...m, streaming: false } : m)),
            );
            // Sync context with the (possibly new) conversation id
            const finalId = liveConvIdRef.current;
            if (finalId !== activeConversationId) {
              suppressReloadRef.current = true;
              setActiveConversationId(finalId);
            }
            refreshConversations();
          },
          (error) => {
            const botContent =
              error === "AI_UNAVAILABLE"
                ? "Hệ thống đang bận, vui lòng thử lại sau vài phút."
                : "Đã có lỗi xảy ra. Vui lòng thử lại sau.";
            setMessages((prev) =>
              prev.map((m) =>
                m.id === botMsgId ? { ...m, loading: false, streaming: false, content: botContent } : m,
              ),
            );
          },
        );
      } catch (err) {
        if (err instanceof RateLimitError) {
          setCooldownSeconds(err.resetInSeconds);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === botMsgId ? { ...m, loading: false, streaming: false, content: err.message } : m,
            ),
          );
        } else {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === botMsgId
                ? { ...m, loading: false, streaming: false, content: "Đã có lỗi xảy ra. Vui lòng thử lại sau." }
                : m,
            ),
          );
        }
      } finally {
        setIsSending(false);
        inputRef.current?.focus();
      }
    },
    [isSending, activeConversationId, setActiveConversationId, refreshConversations],
  );

  function handleSubmit(e: React.SyntheticEvent) {
    e.preventDefault();
    handleSend(input);
  }

  const showSuggestions = messages.length <= 1 && !isLoadingMessages;

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-sky-50 to-indigo-50">
      {/* Header */}
      <header className="flex items-center gap-2 px-4 py-3 bg-white border-b border-sky-100 shadow-sm shrink-0">
        {/* Mobile: hamburger to toggle conversation sidebar */}
        <button
          onClick={toggleSidebar}
          className="md:hidden p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 mr-0.5"
          aria-label="Mở danh sách cuộc trò chuyện"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
            <path fillRule="evenodd" d="M2 4.75A.75.75 0 0 1 2.75 4h14.5a.75.75 0 0 1 0 1.5H2.75A.75.75 0 0 1 2 4.75ZM2 10a.75.75 0 0 1 .75-.75h14.5a.75.75 0 0 1 0 1.5H2.75A.75.75 0 0 1 2 10Zm0 5.25a.75.75 0 0 1 .75-.75h14.5a.75.75 0 0 1 0 1.5H2.75a.75.75 0 0 1-.75-.75Z" clipRule="evenodd" />
          </svg>
        </button>
        <div className="md:hidden w-7 h-7 rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 flex items-center justify-center shadow overflow-hidden">
          <Image src="/student-icon.png" alt="Học sinh" width={20} height={20} loading="eager" />
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="font-bold text-sky-800 text-sm leading-tight">Chat học sinh</h1>
          <p className="text-xs text-sky-500">Việt–Tày/Nùng · Lớp 1–5</p>
        </div>
      </header>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 min-h-0">
        {/* Compact summary banner */}
        {compactSummary && (
          <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">
            <p className="font-semibold mb-1 flex items-center gap-1.5">
              <span>✦</span> Tóm tắt cuộc trò chuyện trước đó
            </p>
            <p className="text-sky-700 leading-relaxed">{compactSummary}</p>
          </div>
        )}

        {/* Loading spinner when switching conversations */}
        {isLoadingMessages ? (
          <div className="flex justify-center py-12">
            <span className="w-6 h-6 border-2 border-sky-400 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          messages.map((msg) => (
            <ChatBubble
              key={msg.id}
              role={msg.role}
              content={msg.content}
              steps={msg.steps}
              vocab={msg.vocab}
              source={msg.source}
              grade={msg.grade}
              loading={msg.loading}
              streaming={msg.streaming}
            />
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggestions */}
      {showSuggestions && (
        <div className="px-4 pb-2 flex flex-wrap gap-2 justify-center shrink-0">
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
        <div className="px-4 pb-2 shrink-0">
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
        className="px-4 py-3 bg-white border-t border-gray-100 flex items-center gap-2 shrink-0"
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
  );
}
