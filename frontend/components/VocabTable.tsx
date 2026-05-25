import { VocabEntry } from "@/lib/api";

interface Props {
  vocab: VocabEntry[];
}

export default function VocabTable({ vocab }: Props) {
  if (!vocab || vocab.length === 0) return null;

  return (
    <div className="mt-3 rounded-xl overflow-hidden border border-amber-200 bg-amber-50">
      <div className="px-3 py-2 bg-amber-100 font-bold text-amber-800 text-sm flex items-center gap-1">
        <span>📚</span> Từ cần nhớ
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-amber-100/60">
            <th className="text-left px-3 py-1.5 font-semibold text-amber-800 border-b border-amber-200">
              Tiếng Việt
            </th>
            <th className="text-left px-3 py-1.5 font-semibold text-amber-800 border-b border-amber-200">
              Tày
            </th>
            <th className="text-left px-3 py-1.5 font-semibold text-amber-800 border-b border-amber-200">
              Nùng
            </th>
          </tr>
        </thead>
        <tbody>
          {vocab.map((entry, i) => (
            <tr
              key={i}
              className={i % 2 === 0 ? "bg-white" : "bg-amber-50/40"}
            >
              <td className="px-3 py-1.5 font-medium text-gray-800">
                {entry.vi}
              </td>
              <td className="px-3 py-1.5 text-gray-700 italic">
                {entry.tay ?? (
                  <span className="text-gray-400 not-italic text-xs">
                    Chưa có
                  </span>
                )}
              </td>
              <td className="px-3 py-1.5 text-gray-700 italic">
                {entry.nung ?? (
                  <span className="text-gray-400 not-italic text-xs">
                    Chưa có
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-3 py-1.5 text-xs text-amber-700 bg-amber-50 border-t border-amber-200">
        * Cách gọi có thể khác nhau theo vùng/phương ngữ
      </p>
    </div>
  );
}
