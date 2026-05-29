"use client";

import { useState, useEffect } from "react";
import DictionaryTable from "@/components/DictionaryTable";
import { removeWord, clearAllWords, getSavedWords, SavedWord } from "@/lib/saved-dictionary";
import { syncVocabDelete, syncVocabClearAll } from "@/lib/vocab-api";
import { getAccessToken } from "@/lib/supabase/client";

async function fetchVocabFromBackend(): Promise<SavedWord[] | null> {
  const token = await getAccessToken();
  if (!token) return null;
  try {
    const res = await fetch("/api/history/vocab", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    const data: Array<{ id: string; vi: string; tay_variants: string[]; nung_variants: string[]; saved_at: string }> =
      await res.json();
    return data.map((item) => ({
      id: item.id,
      vi: item.vi,
      tay_variants: item.tay_variants ?? [],
      nung_variants: item.nung_variants ?? [],
      topic: "",
      saved_at: new Date(item.saved_at).getTime(),
    }));
  } catch {
    return null;
  }
}

export default function DictionaryPage() {
  const [words, setWords] = useState<SavedWord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedTopic, setSelectedTopic] = useState("");

  useEffect(() => {
    setIsLoading(true);
    fetchVocabFromBackend()
      .then((data) => setWords(data ?? getSavedWords()))
      .finally(() => setIsLoading(false));
  }, []);

  function handleRemove(id: string) {
    const word = words.find((w) => w.id === id);
    setWords((prev) => prev.filter((w) => w.id !== id));
    if (word) {
      removeWord(word.vi);
      syncVocabDelete(word.vi);
    }
  }

  function handleClearAll() {
    if (!confirm(`Xóa tất cả ${words.length} từ đã lưu?`)) return;
    setWords([]);
    setSelectedTopic("");
    clearAllWords();
    syncVocabClearAll();
  }

  const topics = Array.from(new Set(words.map((w) => w.topic).filter(Boolean))).sort();
  const filtered = selectedTopic ? words.filter((w) => w.topic === selectedTopic) : words;

  return (
    <div className="h-full overflow-y-auto bg-gradient-to-b from-sky-50 to-indigo-50">
      <header className="sticky top-0 z-10 bg-white border-b border-sky-100 shadow-sm px-4 py-3 flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <h1 className="font-bold text-sky-800 text-base leading-tight">Từ điển của em</h1>
          <p className="text-xs text-sky-500">Đã lưu {words.length} từ</p>
        </div>
        {words.length > 0 && (
          <button
            onClick={handleClearAll}
            className="flex-shrink-0 text-xs px-3 py-1.5 rounded-full border border-red-200 text-red-500 hover:bg-red-50 transition-colors"
          >
            Xóa tất cả
          </button>
        )}
      </header>

      <main className="max-w-2xl mx-auto px-4 py-4 space-y-4">
        {isLoading ? (
          <div className="flex justify-center py-16">
            <span className="w-6 h-6 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <>
            {topics.length > 0 && (
              <select
                value={selectedTopic}
                onChange={(e) => setSelectedTopic(e.target.value)}
                className="w-full sm:w-auto px-3 py-2 rounded-xl border border-gray-200 bg-white text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-sky-300"
              >
                <option value="">Tất cả chủ đề</option>
                {topics.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            )}
            <DictionaryTable words={filtered} onRemove={handleRemove} />
          </>
        )}
      </main>
    </div>
  );
}
