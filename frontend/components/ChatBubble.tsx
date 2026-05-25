"use client";

import { useState, useEffect, useRef } from "react";
import Image from "next/image";
import VocabTable from "./VocabTable";
import { VocabEntry } from "@/lib/api";

interface Props {
  role: "user" | "bot";
  content: string;
  steps?: string[];
  vocab?: VocabEntry[];
  source?: string;
  grade?: number;
  loading?: boolean;
  animate?: boolean;
}

export default function ChatBubble({
  role,
  content,
  steps,
  vocab,
  source,
  grade,
  loading,
  animate = false,
}: Props) {
  const [displayed, setDisplayed] = useState(animate ? "" : content);
  const [isDone, setIsDone] = useState(!animate);
  const indexRef = useRef(0);

  useEffect(() => {
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
  }, [content, animate]);

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
        {loading ? (
          <div className="flex items-center gap-1.5 py-1">
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
          </div>
        ) : (
          <>
            <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
              {displayed}
              {!isDone && (
                <span className="inline-block w-0.5 h-3.5 bg-gray-500 ml-0.5 align-middle animate-pulse" />
              )}
            </p>

            {isDone && steps && steps.length > 0 && (
              <div className="mt-3 bg-sky-50 border border-sky-100 rounded-xl p-3">
                <p className="text-xs font-bold text-sky-700 mb-2 flex items-center gap-1">
                  <span>📝</span> Hướng dẫn giải từng bước
                </p>
                <ol className="space-y-1.5">
                  {steps.map((step, i) => (
                    <li key={i} className="flex gap-2 text-sm text-gray-700">
                      <span className="flex-shrink-0 w-5 h-5 bg-sky-500 text-white rounded-full flex items-center justify-center text-xs font-bold">
                        {i + 1}
                      </span>
                      <span className="leading-relaxed">{step}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {isDone && vocab && <VocabTable vocab={vocab} />}

            {isDone && (source || grade) && (
              <p className="mt-2 text-xs text-gray-400">
                {grade ? `Lớp ${grade}` : ""}
                {grade && source ? " · " : ""}
                {source ?? ""}
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
