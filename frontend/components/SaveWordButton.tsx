"use client";

import { useState } from "react";
import { SavedWord, saveWord, removeWord, isWordSaved } from "@/lib/saved-dictionary";
import { getAccessToken } from "@/lib/supabase/client";

interface SaveWordButtonProps {
  word: SavedWord;
}

async function syncVocabToBackend(word: SavedWord) {
  const token = await getAccessToken();
  if (!token) return;
  await fetch("/api/history/vocab", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      vi: word.vi,
      tay_variants: word.tay_variants,
      nung_variants: word.nung_variants,
    }),
  }).catch(() => {});
}

export default function SaveWordButton({ word }: SaveWordButtonProps) {
  const [saved, setSaved] = useState(() => isWordSaved(word.id));

  function toggle() {
    if (saved) {
      removeWord(word.id);
      setSaved(false);
    } else {
      saveWord({ ...word, saved_at: Date.now() });
      setSaved(true);
      syncVocabToBackend(word);
    }
  }

  return (
    <button
      onClick={toggle}
      className={`text-xs px-2.5 py-1 rounded-full font-medium border transition-colors ${
        saved
          ? "bg-green-100 text-green-700 border-green-300"
          : "bg-white text-gray-600 border-gray-200 hover:bg-green-50 hover:text-green-700 hover:border-green-300"
      }`}
    >
      {saved ? "Đã lưu ✓" : `Lưu "${word.vi}"`}
    </button>
  );
}
