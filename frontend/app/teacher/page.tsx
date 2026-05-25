"use client";

import { useState } from "react";
import Image from "next/image";
import ModeToggle from "@/components/ModeToggle";
import { generateLesson } from "@/lib/api";

const SUBJECTS = ["Toán", "Tiếng Việt", "Tự nhiên và Xã hội", "Khoa học"];
const GRADES = [1, 2, 3, 4, 5];

export default function TeacherPage() {
  const [topic, setTopic] = useState("");
  const [grade, setGrade] = useState<number>(3);
  const [subject, setSubject] = useState("Toán");
  const [result, setResult] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.SyntheticEvent) {
    e.preventDefault();
    if (!topic.trim() || isLoading) return;

    setIsLoading(true);
    setError("");
    setResult("");

    try {
      const res = await generateLesson(topic.trim(), grade, subject);
      setResult(res.lesson_plan);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="flex flex-col min-h-screen bg-gradient-to-b from-emerald-50 to-teal-50">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 bg-white border-b border-emerald-100 shadow-sm sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center shadow overflow-hidden">
            <Image src="/teacher-icon.png" alt="Giáo viên" width={28} height={28} />
          </div>
          <div>
            <h1 className="font-bold text-emerald-800 text-base leading-tight">
              Soạn Giáo Án
            </h1>
            <p className="text-xs text-emerald-500">Dành cho giáo viên</p>
          </div>
        </div>
        <ModeToggle />
      </header>

      <main className="flex-1 px-4 py-6 max-w-2xl mx-auto w-full space-y-5">
        {/* Form */}
        <div className="bg-white rounded-2xl shadow-sm border border-emerald-100 p-5">
          <h2 className="font-bold text-gray-700 mb-4 flex items-center gap-2">
            <span className="text-emerald-500 text-lg">📋</span>
            Thông tin giáo án
          </h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-semibold text-gray-600 mb-1.5">
                Chủ đề / Bài học <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="VD: Phép nhân hai chữ số, Chu vi hình chữ nhật..."
                className="w-full px-4 py-3 rounded-xl border border-gray-200 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-300 text-sm text-gray-800 placeholder:text-gray-400"
                disabled={isLoading}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-semibold text-gray-600 mb-1.5">
                  Lớp
                </label>
                <select
                  value={grade}
                  onChange={(e) => setGrade(Number(e.target.value))}
                  className="w-full px-4 py-3 rounded-xl border border-gray-200 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-300 text-sm text-gray-800"
                  disabled={isLoading}
                >
                  {GRADES.map((g) => (
                    <option key={g} value={g}>
                      Lớp {g}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-600 mb-1.5">
                  Môn học
                </label>
                <select
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  className="w-full px-4 py-3 rounded-xl border border-gray-200 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-300 text-sm text-gray-800"
                  disabled={isLoading}
                >
                  {SUBJECTS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <button
              type="submit"
              disabled={!topic.trim() || isLoading}
              className="w-full py-3 rounded-xl bg-emerald-500 text-white font-bold text-sm hover:bg-emerald-600 active:scale-[0.98] transition-all shadow disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {isLoading ? (
                <>
                  <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Đang tạo giáo án...
                </>
              ) : (
                <>
                  <span>✨</span>
                  Tạo giáo án
                </>
              )}
            </button>
          </form>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700 flex items-start gap-2">
            <span>⚠️</span>
            <span>Có lỗi xảy ra: {error}. Vui lòng thử lại.</span>
          </div>
        )}

        {/* Result */}
        {result && (
          <div className="bg-white rounded-2xl shadow-sm border border-emerald-100 p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-bold text-gray-700 flex items-center gap-2">
                <span className="text-emerald-500 text-lg">📄</span>
                Giáo án được tạo
              </h2>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(result);
                }}
                className="text-xs px-3 py-1.5 bg-emerald-50 text-emerald-600 rounded-lg hover:bg-emerald-100 transition-colors font-medium border border-emerald-200"
              >
                📋 Sao chép
              </button>
            </div>
            <div className="prose prose-sm max-w-none text-gray-700 whitespace-pre-wrap text-sm leading-relaxed bg-gray-50 rounded-xl p-4 border border-gray-100">
              {result}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!result && !isLoading && (
          <div className="text-center py-8 text-gray-400">
            <div className="text-5xl mb-3">📝</div>
            <p className="text-sm">
              Nhập thông tin giáo án và nhấn &quot;Tạo giáo án&quot; để bắt đầu
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
