import { SavedWord } from "@/lib/saved-dictionary";

interface Props {
  words: SavedWord[];
  onRemove: (id: string) => void;
}

export default function DictionaryTable({ words, onRemove }: Props) {
  if (words.length === 0) {
    return (
      <div className="text-center py-16 text-gray-500">
        <p className="text-5xl mb-4">📖</p>
        <p className="text-base font-medium">Chưa có từ nào được lưu.</p>
        <p className="text-sm mt-1 text-gray-400">
          Hãy chat và bấm <strong className="text-green-600">Lưu từ này</strong>!
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl overflow-hidden border border-amber-200">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-amber-100">
            <th className="px-3 py-2.5 text-left font-semibold text-amber-800 border-b border-amber-200 w-10">
              STT
            </th>
            <th className="px-3 py-2.5 text-left font-semibold text-amber-800 border-b border-amber-200">
              Tiếng Việt
            </th>
            <th className="px-3 py-2.5 text-left font-semibold text-amber-800 border-b border-amber-200">
              Tiếng Tày
            </th>
            <th className="px-3 py-2.5 text-left font-semibold text-amber-800 border-b border-amber-200">
              Tiếng Nùng
            </th>
            <th className="hidden sm:table-cell px-3 py-2.5 text-left font-semibold text-amber-800 border-b border-amber-200">
              Chủ đề
            </th>
            <th className="px-2 py-2.5 border-b border-amber-200 w-8" />
          </tr>
        </thead>
        <tbody>
          {words.map((word, i) => (
            <tr key={word.id} className={i % 2 === 0 ? "bg-white" : "bg-amber-50/40"}>
              <td className="px-3 py-2 text-gray-400 text-xs">{i + 1}</td>
              <td className="px-3 py-2 font-medium text-gray-800">{word.vi}</td>
              <td className="px-3 py-2 text-gray-700 italic whitespace-pre-line">
                {word.tay_variants.length > 0 ? (
                  word.tay_variants.join("\n")
                ) : (
                  <span className="text-gray-400 not-italic text-xs">Chưa có</span>
                )}
              </td>
              <td className="px-3 py-2 text-gray-700 italic whitespace-pre-line">
                {word.nung_variants.length > 0 ? (
                  word.nung_variants.join("\n")
                ) : (
                  <span className="text-gray-400 not-italic text-xs">Chưa có</span>
                )}
              </td>
              <td className="hidden sm:table-cell px-3 py-2 text-gray-500 text-xs">
                {word.topic || "—"}
              </td>
              <td className="px-2 py-2 text-center">
                <button
                  onClick={() => onRemove(word.id)}
                  className="w-6 h-6 flex items-center justify-center text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-full transition-colors text-base font-bold leading-none"
                  aria-label="Xóa từ này"
                >
                  ×
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-3 py-2 text-xs text-amber-700 bg-amber-50 border-t border-amber-200">
        * Cách gọi có thể khác nhau theo vùng/phương ngữ
      </p>
    </div>
  );
}
