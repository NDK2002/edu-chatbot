"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Image from "next/image";
import {
  generateLesson,
  fetchLessonHistory,
  updateLesson,
  type LessonPlanResponse,
  type LessonHistoryItem,
  type LessonActivity,
} from "@/lib/api";

const SUBJECTS = ["Toán", "Tiếng Việt", "Tự nhiên và Xã hội", "Khoa học"];
const GRADES = [1, 2, 3, 4, 5];
const DRAFT_KEY = "edu_lesson_draft";

interface DraftPayload {
  plan: LessonPlanResponse;
  savedAt: string;
}

export default function TeacherPage() {
  const [topic, setTopic] = useState("");
  const [grade, setGrade] = useState<number>(3);
  const [subject, setSubject] = useState("Toán");
  const [result, setResult] = useState<LessonPlanResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const [isEditing, setIsEditing] = useState(false);
  const [editDraft, setEditDraft] = useState<LessonPlanResponse | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [syncError, setSyncError] = useState("");

  const [draftMeta, setDraftMeta] = useState<{ topic: string; savedAt: string } | null>(null);
  const draftTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [history, setHistory] = useState<LessonHistoryItem[]>([]);
  const [filterGrade, setFilterGrade] = useState<number | null>(null);
  const [filterSubject, setFilterSubject] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  // On mount: check localStorage for unsaved draft
  useEffect(() => {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (!raw) return;
      const { plan, savedAt } = JSON.parse(raw) as DraftPayload;
      if (plan?.topic) setDraftMeta({ topic: plan.topic, savedAt });
    } catch {
      localStorage.removeItem(DRAFT_KEY);
    }
  }, []);

  // Debounce-save editDraft to localStorage while editing
  useEffect(() => {
    if (!isEditing || !editDraft) return;
    if (draftTimerRef.current) clearTimeout(draftTimerRef.current);
    draftTimerRef.current = setTimeout(() => {
      try {
        localStorage.setItem(DRAFT_KEY, JSON.stringify({ plan: editDraft, savedAt: new Date().toISOString() }));
      } catch {
        // localStorage unavailable or full — silently ignore
      }
    }, 500);
    return () => {
      if (draftTimerRef.current) clearTimeout(draftTimerRef.current);
    };
  }, [isEditing, editDraft]);

  const loadHistory = useCallback(async () => {
    try {
      const items = await fetchLessonHistory(filterGrade, filterSubject);
      setHistory(items);
    } catch {
      // keep stale history
    }
  }, [filterGrade, filterSubject]);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  async function handleSubmit(e: React.SyntheticEvent) {
    e.preventDefault();
    if (!topic.trim() || isLoading) return;
    setIsLoading(true);
    setError("");
    setResult(null);
    setIsEditing(false);
    setEditDraft(null);
    setSyncError("");
    // Starting fresh — discard any draft
    localStorage.removeItem(DRAFT_KEY);
    setDraftMeta(null);
    try {
      const res = await generateLesson(topic.trim(), grade, subject);
      setResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsLoading(false);
    }
    loadHistory().catch(() => {});
  }

  function loadFromHistory(item: LessonHistoryItem) {
    setShowHistory(false);
    setError("");
    setSyncError("");

    // If there's an unsaved draft for this exact lesson, resume editing it
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (raw) {
        const { plan } = JSON.parse(raw) as DraftPayload;
        if (plan?.id === item.id) {
          setResult(plan);
          setEditDraft({
            ...plan,
            objectives: [...plan.objectives],
            activities: plan.activities.map((a) => ({ ...a })),
            exercises: [...plan.exercises],
          });
          setTopic(plan.topic);
          setGrade(plan.grade);
          setSubject(plan.subject);
          setIsEditing(true);
          setDraftMeta(null);
          return;
        }
      }
    } catch {
      localStorage.removeItem(DRAFT_KEY);
    }

    // No matching draft — load saved version from Supabase
    setResult(item);
    setTopic(item.topic);
    setGrade(item.grade);
    setSubject(item.subject);
    setIsEditing(false);
    setEditDraft(null);
    localStorage.removeItem(DRAFT_KEY);
    setDraftMeta(null);
  }

  function startEditing() {
    if (!result) return;
    setSyncError("");
    setEditDraft({
      ...result,
      objectives: [...result.objectives],
      activities: result.activities.map((a) => ({ ...a })),
      exercises: [...result.exercises],
    });
    setIsEditing(true);
  }

  function cancelEditing() {
    setIsEditing(false);
    setEditDraft(null);
    localStorage.removeItem(DRAFT_KEY);
    setDraftMeta(null);
  }

  async function saveEditing() {
    if (!editDraft) return;
    setResult(editDraft);
    setIsEditing(false);
    setEditDraft(null);
    localStorage.removeItem(DRAFT_KEY);
    setDraftMeta(null);
    setSyncError("");

    if (editDraft.id) {
      setIsSaving(true);
      try {
        await updateLesson(editDraft.id, {
          objectives: editDraft.objectives,
          activities: editDraft.activities,
          exercises: editDraft.exercises,
        });
      } catch {
        setSyncError("Đã lưu trên thiết bị nhưng chưa đồng bộ lên máy chủ.");
      } finally {
        setIsSaving(false);
      }
    }
  }

  function recoverDraft() {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (!raw) return;
      const { plan } = JSON.parse(raw) as DraftPayload;
      setResult(plan);
      setEditDraft({
        ...plan,
        objectives: [...plan.objectives],
        activities: plan.activities.map((a) => ({ ...a })),
        exercises: [...plan.exercises],
      });
      setTopic(plan.topic);
      setGrade(plan.grade);
      setSubject(plan.subject);
      setIsEditing(true);
      setDraftMeta(null);
    } catch {
      localStorage.removeItem(DRAFT_KEY);
      setDraftMeta(null);
    }
  }

  function discardDraft() {
    localStorage.removeItem(DRAFT_KEY);
    setDraftMeta(null);
  }

  return (
    <div className="h-full flex flex-col bg-gradient-to-b from-emerald-50 to-teal-50">
      {/* Header */}
      <header className="flex items-center gap-2 px-4 py-3 bg-white border-b border-emerald-100 shadow-sm sticky top-0 z-10">
        <div className="md:hidden w-8 h-8 rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center shadow overflow-hidden">
          <Image src="/teacher-icon.png" alt="Giáo viên" width={22} height={22} />
        </div>
        <div className="flex-1">
          <h1 className="font-bold text-emerald-800 text-sm leading-tight">Soạn Giáo Án</h1>
          <p className="text-xs text-emerald-500">Dành cho giáo viên · RAG từ SGK Cánh Diều</p>
        </div>
        <button
          className="md:hidden px-3 py-1.5 text-xs font-medium bg-emerald-50 text-emerald-700 rounded-lg border border-emerald-200 hover:bg-emerald-100 transition-colors"
          onClick={() => setShowHistory((v) => !v)}
        >
          {showHistory ? "Đóng" : "Lịch sử"}
        </button>
      </header>

      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* History Panel */}
        <aside
          className={`${
            showHistory ? "flex" : "hidden"
          } md:flex w-full md:w-60 shrink-0 flex-col bg-white border-r border-emerald-100 overflow-hidden absolute inset-0 md:relative md:inset-auto z-10`}
        >
          <div className="p-3 border-b border-emerald-100 shrink-0">
            <p className="text-xs font-bold text-gray-600 mb-2">📋 Lịch sử giáo án</p>
            <div className="flex gap-1.5">
              <select
                value={filterGrade ?? ""}
                onChange={(e) => setFilterGrade(e.target.value ? Number(e.target.value) : null)}
                className="flex-1 text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-gray-50 focus:outline-none focus:ring-1 focus:ring-emerald-300"
              >
                <option value="">Tất cả lớp</option>
                {GRADES.map((g) => (
                  <option key={g} value={g}>Lớp {g}</option>
                ))}
              </select>
              <select
                value={filterSubject ?? ""}
                onChange={(e) => setFilterSubject(e.target.value || null)}
                className="flex-1 text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-gray-50 focus:outline-none focus:ring-1 focus:ring-emerald-300"
              >
                <option value="">Tất cả môn</option>
                {SUBJECTS.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
            {history.length === 0 && (
              <p className="text-xs text-gray-400 text-center py-8">Chưa có giáo án nào</p>
            )}
            {history.map((item) => (
              <button
                key={item.id}
                onClick={() => loadFromHistory(item)}
                className="w-full text-left px-3 py-2.5 rounded-xl border border-gray-100 bg-gray-50 hover:bg-emerald-50 hover:border-emerald-200 transition-colors"
              >
                <p className="text-xs font-semibold text-gray-700 truncate">{item.topic}</p>
                <p className="text-xs text-gray-400">
                  {item.subject} · Lớp {item.grade}
                </p>
                <p className="text-xs text-gray-400">
                  {new Date(item.created_at).toLocaleDateString("vi-VN")}
                </p>
              </button>
            ))}
          </div>
        </aside>

        {/* Main Area */}
        <main className="flex-1 overflow-y-auto">
          <div className="px-4 py-5 max-w-2xl mx-auto w-full space-y-4">

            {/* Draft recovery banner */}
            {draftMeta && !result && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
                <span className="text-amber-500 text-lg shrink-0">📝</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-amber-800">Có bản nháp chưa lưu</p>
                  <p className="text-xs text-amber-600 truncate">
                    &ldquo;{draftMeta.topic}&rdquo; &middot;{" "}
                    {new Date(draftMeta.savedAt).toLocaleString("vi-VN")}
                  </p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={discardDraft}
                    className="text-xs text-gray-500 hover:text-gray-700 font-medium px-2 py-1.5"
                  >
                    Bỏ qua
                  </button>
                  <button
                    onClick={recoverDraft}
                    className="text-xs text-amber-700 hover:text-amber-800 font-semibold bg-amber-100 hover:bg-amber-200 px-3 py-1.5 rounded-lg transition-colors"
                  >
                    Khôi phục
                  </button>
                </div>
              </div>
            )}

            {/* Form */}
            <div className="bg-white rounded-2xl shadow-sm border border-emerald-100 p-5">
              <h2 className="font-bold text-gray-700 mb-4 flex items-center gap-2">
                <span className="text-emerald-500 text-lg">📝</span>
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
                    placeholder="VD: Bảng nhân 3, Chu vi hình chữ nhật..."
                    className="w-full px-4 py-3 rounded-xl border border-gray-200 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-emerald-300 focus:border-emerald-300 text-sm text-gray-800 placeholder:text-gray-400"
                    disabled={isLoading}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-semibold text-gray-600 mb-1.5">Lớp</label>
                    <select
                      value={grade}
                      onChange={(e) => setGrade(Number(e.target.value))}
                      className="w-full px-4 py-3 rounded-xl border border-gray-200 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-emerald-300 text-sm text-gray-800"
                      disabled={isLoading}
                    >
                      {GRADES.map((g) => (
                        <option key={g} value={g}>Lớp {g}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-gray-600 mb-1.5">Môn học</label>
                    <select
                      value={subject}
                      onChange={(e) => setSubject(e.target.value)}
                      className="w-full px-4 py-3 rounded-xl border border-gray-200 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-emerald-300 text-sm text-gray-800"
                      disabled={isLoading}
                    >
                      {SUBJECTS.map((s) => (
                        <option key={s} value={s}>{s}</option>
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
                    <><span>✨</span>Tạo giáo án</>
                  )}
                </button>
              </form>
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700 flex items-start gap-2">
                <span>⚠️</span>
                <span>Có lỗi xảy ra: {error}. Vui lòng thử lại.</span>
              </div>
            )}

            {syncError && (
              <div className="bg-orange-50 border border-orange-200 rounded-xl p-3 text-sm text-orange-700 flex items-center gap-2">
                <span>⚠️</span>
                <span>{syncError}</span>
              </div>
            )}

            {/* Edit action bar */}
            {result && (
              <div className="flex items-center justify-end gap-2">
                {!isEditing ? (
                  <button
                    onClick={startEditing}
                    className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-emerald-700 bg-white border border-emerald-200 rounded-xl hover:bg-emerald-50 transition-colors shadow-sm"
                  >
                    ✏️ Chỉnh sửa
                  </button>
                ) : (
                  <>
                    <button
                      onClick={cancelEditing}
                      className="px-4 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-200 rounded-xl hover:bg-gray-50 transition-colors"
                    >
                      Hủy
                    </button>
                    <button
                      onClick={saveEditing}
                      disabled={isSaving}
                      className="px-4 py-2 text-sm font-medium text-white bg-emerald-500 rounded-xl hover:bg-emerald-600 transition-colors shadow-sm disabled:opacity-60 flex items-center gap-1.5"
                    >
                      {isSaving ? (
                        <>
                          <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                          Đang lưu...
                        </>
                      ) : "💾 Lưu"}
                    </button>
                  </>
                )}
              </div>
            )}

            {result && !isEditing && <LessonPlanView plan={result} />}
            {result && isEditing && editDraft && (
              <LessonPlanEditor draft={editDraft} onChange={setEditDraft} />
            )}

            {!result && !isLoading && !error && (
              <div className="text-center py-10 text-gray-400">
                <div className="text-5xl mb-3">📝</div>
                <p className="text-sm">
                  Nhập thông tin giáo án và nhấn &quot;Tạo giáo án&quot; để bắt đầu
                </p>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

function LessonPlanView({ plan }: { plan: LessonPlanResponse }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 px-1">
        <span className="text-xs font-semibold text-gray-500">
          {plan.subject} · Lớp {plan.grade}
        </span>
        {plan.rag_used ? (
          <span className="text-xs bg-emerald-100 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full font-medium">
            📚 SGK Cánh Diều
          </span>
        ) : (
          <span className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full font-medium">
            🤖 AI tổng hợp · chưa kiểm chứng từ SGK
          </span>
        )}
      </div>

      {/* Mục tiêu — green */}
      <div className="bg-white rounded-2xl border border-green-100 border-l-4 border-l-green-500 p-4">
        <h3 className="text-xs font-bold text-green-700 mb-2 tracking-wide uppercase">
          🎯 Mục tiêu
        </h3>
        <ul className="space-y-1.5">
          {plan.objectives.map((obj, i) => (
            <li key={i} className="text-sm text-gray-700 flex gap-2">
              <span className="text-green-400 mt-0.5 shrink-0">•</span>
              {obj}
            </li>
          ))}
        </ul>
      </div>

      {/* Hoạt động — blue */}
      <div className="bg-white rounded-2xl border border-blue-100 border-l-4 border-l-blue-500 p-4">
        <h3 className="text-xs font-bold text-blue-700 mb-2 tracking-wide uppercase">
          📚 Hoạt động dạy học
        </h3>
        <div className="space-y-2">
          {plan.activities.map((act, i) => (
            <div key={i} className="flex gap-3">
              <span className="text-xs font-bold text-blue-400 mt-0.5 whitespace-nowrap shrink-0">
                {act.step}. {act.duration}
              </span>
              <span className="text-sm text-gray-700">{act.description}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Bài tập — amber */}
      <div className="bg-white rounded-2xl border border-amber-100 border-l-4 border-l-amber-500 p-4">
        <h3 className="text-xs font-bold text-amber-700 mb-2 tracking-wide uppercase">
          ✍️ Bài tập
        </h3>
        <ul className="space-y-1.5">
          {plan.exercises.map((ex, i) => (
            <li key={i} className="text-sm text-gray-700 flex gap-2">
              <span className="text-amber-500 font-bold shrink-0">{i + 1}.</span>
              {ex}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function LessonPlanEditor({
  draft,
  onChange,
}: {
  draft: LessonPlanResponse;
  onChange: (d: LessonPlanResponse) => void;
}) {
  function setObjective(i: number, val: string) {
    const objectives = [...draft.objectives];
    objectives[i] = val;
    onChange({ ...draft, objectives });
  }
  function removeObjective(i: number) {
    onChange({ ...draft, objectives: draft.objectives.filter((_, idx) => idx !== i) });
  }
  function addObjective() {
    onChange({ ...draft, objectives: [...draft.objectives, ""] });
  }

  function setActivity(i: number, field: keyof LessonActivity, val: string | number) {
    const activities = draft.activities.map((a, idx) =>
      idx === i ? { ...a, [field]: val } : a
    );
    onChange({ ...draft, activities });
  }
  function removeActivity(i: number) {
    const activities = draft.activities
      .filter((_, idx) => idx !== i)
      .map((a, idx) => ({ ...a, step: idx + 1 }));
    onChange({ ...draft, activities });
  }
  function addActivity() {
    onChange({
      ...draft,
      activities: [
        ...draft.activities,
        { step: draft.activities.length + 1, duration: "5 phút", description: "" },
      ],
    });
  }

  function setExercise(i: number, val: string) {
    const exercises = [...draft.exercises];
    exercises[i] = val;
    onChange({ ...draft, exercises });
  }
  function removeExercise(i: number) {
    onChange({ ...draft, exercises: draft.exercises.filter((_, idx) => idx !== i) });
  }
  function addExercise() {
    onChange({ ...draft, exercises: [...draft.exercises, ""] });
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 px-1 flex-wrap">
        <span className="text-xs font-semibold text-gray-500">
          {draft.subject} · Lớp {draft.grade}
        </span>
        {draft.rag_used && (
          <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-medium">
            📚 RAG từ SGK
          </span>
        )}
        <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium ml-auto">
          ✏️ Đang chỉnh sửa
        </span>
      </div>

      {/* Mục tiêu */}
      <div className="bg-white rounded-2xl border border-green-100 border-l-4 border-l-green-500 p-4">
        <h3 className="text-xs font-bold text-green-700 mb-2 tracking-wide uppercase">🎯 Mục tiêu</h3>
        <div className="space-y-2">
          {draft.objectives.map((obj, i) => (
            <div key={i} className="flex gap-2 items-start">
              <span className="text-green-400 mt-2.5 shrink-0">•</span>
              <textarea
                value={obj}
                onChange={(e) => setObjective(i, e.target.value)}
                rows={2}
                className="flex-1 text-sm text-gray-700 border border-gray-200 rounded-lg px-3 py-2 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-green-300 resize-none"
              />
              <button
                onClick={() => removeObjective(i)}
                className="text-gray-300 hover:text-red-400 transition-colors text-xl leading-none mt-2 shrink-0"
                title="Xóa"
              >×</button>
            </div>
          ))}
          <button
            onClick={addObjective}
            className="text-xs text-green-600 hover:text-green-700 font-medium flex items-center gap-1 mt-1"
          >
            + Thêm mục tiêu
          </button>
        </div>
      </div>

      {/* Hoạt động */}
      <div className="bg-white rounded-2xl border border-blue-100 border-l-4 border-l-blue-500 p-4">
        <h3 className="text-xs font-bold text-blue-700 mb-2 tracking-wide uppercase">📚 Hoạt động dạy học</h3>
        <div className="space-y-3">
          {draft.activities.map((act, i) => (
            <div key={i} className="flex gap-2 items-start">
              <span className="text-xs font-bold text-blue-400 mt-2.5 shrink-0 w-5">{act.step}.</span>
              <div className="flex-1 space-y-1.5">
                <input
                  type="text"
                  value={act.duration}
                  onChange={(e) => setActivity(i, "duration", e.target.value)}
                  placeholder="Thời gian (VD: 10 phút)"
                  className="w-full text-xs border border-gray-200 rounded-lg px-3 py-1.5 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-300"
                />
                <textarea
                  value={act.description}
                  onChange={(e) => setActivity(i, "description", e.target.value)}
                  rows={2}
                  className="w-full text-sm text-gray-700 border border-gray-200 rounded-lg px-3 py-2 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-300 resize-none"
                />
              </div>
              <button
                onClick={() => removeActivity(i)}
                className="text-gray-300 hover:text-red-400 transition-colors text-xl leading-none mt-2 shrink-0"
                title="Xóa"
              >×</button>
            </div>
          ))}
          <button
            onClick={addActivity}
            className="text-xs text-blue-600 hover:text-blue-700 font-medium flex items-center gap-1"
          >
            + Thêm hoạt động
          </button>
        </div>
      </div>

      {/* Bài tập */}
      <div className="bg-white rounded-2xl border border-amber-100 border-l-4 border-l-amber-500 p-4">
        <h3 className="text-xs font-bold text-amber-700 mb-2 tracking-wide uppercase">✍️ Bài tập</h3>
        <div className="space-y-2">
          {draft.exercises.map((ex, i) => (
            <div key={i} className="flex gap-2 items-start">
              <span className="text-amber-500 font-bold text-sm mt-2 shrink-0">{i + 1}.</span>
              <textarea
                value={ex}
                onChange={(e) => setExercise(i, e.target.value)}
                rows={2}
                className="flex-1 text-sm text-gray-700 border border-gray-200 rounded-lg px-3 py-2 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-amber-300 resize-none"
              />
              <button
                onClick={() => removeExercise(i)}
                className="text-gray-300 hover:text-red-400 transition-colors text-xl leading-none mt-2 shrink-0"
                title="Xóa"
              >×</button>
            </div>
          ))}
          <button
            onClick={addExercise}
            className="text-xs text-amber-600 hover:text-amber-700 font-medium flex items-center gap-1"
          >
            + Thêm bài tập
          </button>
        </div>
      </div>
    </div>
  );
}
