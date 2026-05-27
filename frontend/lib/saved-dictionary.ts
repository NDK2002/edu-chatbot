export interface SavedWord {
  id: string
  vi: string
  tay_variants: string[]
  nung_variants: string[]
  topic: string
  saved_at: number
}

const STORAGE_KEY = "edu_saved_dictionary"

export function getSavedWords(): SavedWord[] {
  if (typeof window === "undefined") return []
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as SavedWord[]) : []
  } catch {
    return []
  }
}

export function saveWord(word: SavedWord): void {
  const words = getSavedWords()
  if (words.some((w) => w.id === word.id)) return
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...words, word]))
}

export function removeWord(id: string): void {
  const words = getSavedWords().filter((w) => w.id !== id)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(words))
}

export function clearAllWords(): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify([]))
}

export function isWordSaved(id: string): boolean {
  return getSavedWords().some((w) => w.id === id)
}

export function getTopics(): string[] {
  const words = getSavedWords()
  const topics = new Set(words.map((w) => w.topic).filter(Boolean))
  return Array.from(topics).sort()
}
