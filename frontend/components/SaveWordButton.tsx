"use client";

import { useState } from "react";
import { SavedWord, saveWord, removeWord, isWordSaved } from "@/lib/saved-dictionary";
import { syncVocabSave, syncVocabDelete } from "@/lib/vocab-api";

interface SaveWordButtonProps {
  word: SavedWord;
}

export default function SaveWordButton({ word }: SaveWordButtonProps) {
  const [saved, setSaved] = useState(() => isWordSaved(word.id));

  function toggle() {
    if (saved) {
      removeWord(word.id);
      setSaved(false);
      syncVocabDelete(word.vi);
    } else {
      saveWord({ ...word, saved_at: Date.now() });
      setSaved(true);
      syncVocabSave({ vi: word.vi, tay_variants: word.tay_variants, nung_variants: word.nung_variants });
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
