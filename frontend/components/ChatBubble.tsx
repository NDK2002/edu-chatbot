"use client";

import { useState, useEffect, useRef } from "react";
import Image from "next/image";
import VocabTable from "./VocabTable";
import SaveWordButton from "./SaveWordButton";
import { VocabEntry } from "@/lib/api";
import { SavedWord } from "@/lib/saved-dictionary";

function vocabEntryToSavedWord(entry: VocabEntry): SavedWord {
  return {
    id: "vocab_" + entry.vi.trim().replace(/\s+/g, "_"),
    vi: entry.vi,
    tay_variants: entry.tay ? [entry.tay] : [],
    nung_variants: entry.nung ? [entry.nung] : [],
    topic: "",
    saved_at: 0,
  };
}

interface Props {
  role: "user" | "bot";
  content: string;
  vocab?: VocabEntry[];
  source?: string;
  grade?: number;
  loading?: boolean;
  animate?: boolean;
  streaming?: boolean;
}

function SourceBadge({ source, hasVocab }: { source?: string; hasVocab?: boolean }) {
  if (!source || source === "safety") return null;
  if (source === "vector") {
    return (
      <span className="text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full font-medium">
        📚 SGK Cánh Diều
      </span>
    );
  }
  if (source === "rule_engine") {
    return (
      <span className="text-xs bg-sky-50 text-sky-700 border border-sky-200 px-2 py-0.5 rounded-full font-medium">
        🔢 Tính toán chính xác
      </span>
    );
  }
  // "llm": explanation from AI, but vocab (if any) came from dictionary RAG
  if (hasVocab) {
    return (
      <span className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full font-medium">
        🤖 AI giải thích · 📚 Từ điển Tày/Nùng
      </span>
    );
  }
  return (
    <span className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full font-medium">
      🤖 AI tổng hợp · chưa kiểm chứng từ SGK
    </span>
  );
}

export default function ChatBubble({
  role,
  content,
  vocab,
  source,
  grade,
  loading,
  animate = false,
  streaming = false,
}: Props) {
  const [displayed, setDisplayed] = useState(animate ? "" : content);
  const [isDone, setIsDone] = useState(!animate);
  const indexRef = useRef(0);

  useEffect(() => {
    // Real-time streaming: parent accumulates text, just mirror it with cursor
    if (streaming) {
      setDisplayed(content);
      setIsDone(false);
      return;
    }

    if (!animate || !content) {
      setDisplayed(content);
      setIsDone(true);
      return;
    }

    indexRef.current = 0;
    setDisplayed("");
    setIsDone(false);

    // Aim for ~4s total regardless of length
    const chunkSize = Math.max(1, Math.ceil(content.length / 160));

    const id = setInterval(() => {
      indexRef.current += chunkSize;
      if (indexRef.current >= content.length) {
        setDisplayed(content);
        setIsDone(true);
        clearInterval(id);
      } else {
        setDisplayed(content.slice(0, indexRef.current));
      }
    }, 25);

    return () => clearInterval(id);
  }, [content, animate, streaming]);

  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] bg-sky-500 text-white rounded-2xl rounded-tr-sm px-4 py-3 shadow text-sm leading-relaxed">
          {content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start gap-2">
      <div className="flex-shrink-0 w-9 h-9 rounded-full bg-gradient-to-br from-violet-500 to-sky-500 flex items-center justify-center shadow overflow-hidden">
        <Image src="/bot-icon.png" alt="Bot" width={24} height={24} />
      </div>
      <div className="max-w-[85%] bg-white border border-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
        {loading || (streaming && !content) ? (
          <div className="flex items-center gap-1.5 py-1">
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
          </div>
        ) : (
          <>
            <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
              {displayed}
              {(!isDone || streaming) && (
                <span className="inline-block w-0.5 h-3.5 bg-gray-500 ml-0.5 align-middle animate-pulse" />
              )}
            </p>

{isDone && !streaming && vocab && vocab.length > 0 && (
              <>
                <VocabTable vocab={vocab} />
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {vocab.map((entry, i) => (
                    <SaveWordButton key={i} word={vocabEntryToSavedWord(entry)} />
                  ))}
                </div>
              </>
            )}

            {isDone && !streaming && (source || grade) && (
              <div className="mt-2 flex items-center gap-1.5 flex-wrap">
                {grade && (
                  <span className="text-xs text-gray-400">Lớp {grade}</span>
                )}
                <SourceBadge source={source} hasVocab={!!vocab?.length} />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
