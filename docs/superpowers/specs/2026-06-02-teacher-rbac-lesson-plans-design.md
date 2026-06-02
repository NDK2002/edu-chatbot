# Design: Teacher RBAC + RAG-Augmented Lesson Plan Feature

**Date:** 2026-06-02  
**Branch:** `feature/teacher-rbac-lesson-plans`  
**Status:** Approved

---

## Overview

Two interrelated features built on the same branch:

1. **RBAC (Role-Based Access Control):** Enforce teacher/student roles throughout the app — redirect after login, hide teacher tab from students, block `/teacher` route.
2. **Teacher Lesson Plan:** Upgrade the existing lesson generation page with RAG-augmented output, structured section cards, and a filterable lesson history panel.

---

## Current State

- `profiles.role` exists in Supabase DB (populated via trigger from `user_metadata` at registration).
- Register form captures role (student/teacher) but login/register always redirects to `/student`.
- `/teacher` route is accessible to any authenticated user.
- Mobile nav shows "Giáo viên" tab for all users.
- `POST /teacher/lesson` calls Gemini with a plain-text prompt (references H'Mông incorrectly, returns unstructured text).
- No lesson plan history or persistence.

---

## Section 1: RBAC & Auth Flow

### Approach

Next.js Middleware (`middleware.ts`) is the single enforcement point for all auth and role checks. This prevents any page from rendering before access is verified.

### 1A — Login / Register Redirect

`app/auth/actions.ts`: after successful login or register, read `role` from `user_metadata` and redirect accordingly.

```
role === 'teacher'  →  redirect('/teacher')
role === 'student'  →  redirect('/student')
```

### 1B — middleware.ts (new file)

Runs on every request to protected routes. Logic:

```
Request → read Supabase session from cookie
  ├─ No session + protected route  →  redirect /login
  ├─ role=student + path starts with /teacher  →  redirect /student
  └─ role=teacher  →  allow all routes (chat, dictionary, teacher)
```

Students can access `/student` and `/dictionary`. Teachers can access all three. Only `/teacher` is gated.

### 1C — Role-Aware Navigation

`(protected)/layout.tsx`: reads `role` from `user_metadata`, passes it as prop to `ProtectedShell`.

`components/ProtectedShell.tsx`: renders teacher tab in mobile nav and sidebar conditionally — only when `role === 'teacher'`.

| Role | Visible tabs |
|------|-------------|
| student | Chat, Từ điển |
| teacher | Chat, Từ điển, Soạn bài |

### 1D — Files Changed

| File | Change |
|------|--------|
| `middleware.ts` (new) | Block `/teacher` for students; refresh session cookie |
| `app/auth/actions.ts` | Role-based redirect after login and register |
| `app/(protected)/layout.tsx` | Read role, pass to ProtectedShell |
| `components/ProtectedShell.tsx` | Conditionally render teacher nav item |

---

## Section 2: Teacher Lesson Plan Feature

### Layout

Two-column layout on desktop:
- **Left panel (220px):** Lesson history list with filter dropdowns (subject, grade). Items are clickable to reload a past lesson plan.
- **Right panel (flex):** Form at top (topic + grade + subject + submit button), output section cards below.

On mobile: single column. History panel is hidden by default behind a "Lịch sử" toggle button at the top of the page; tapping it shows/hides the panel above the form.

### Output Format — Section Cards

Gemini returns structured JSON. Frontend renders three distinct colored cards:

| Card | Color | Content |
|------|-------|---------|
| 🎯 Mục tiêu | Green left border | `objectives[]` — bullet list |
| 📚 Hoạt động dạy học | Blue left border | `activities[]` — numbered steps with duration |
| ✍️ Bài tập | Amber left border | `exercises[]` — practice problems |

### Backend Flow — POST /teacher/lesson

```
1. Receive: {topic, grade, subject}
2. Search Qdrant:
   - Collection: edu_math_canh_dieu
   - Filter: subject + book_set=Cánh Diều
   - Query: topic text → top 5 chunks
3a. Chunks found (score ≥ 0.82):
    → Inject SGK context into Gemini prompt
3b. No chunks (subject not in Qdrant yet):
    → Gemini fallback (no RAG context)
4. Gemini prompt (Tày/Nùng context, not H'Mông):
   "Dựa trên nội dung SGK Cánh Diều này, soạn giáo án môn {subject}
    lớp {grade}, chủ đề: {topic}.
    Dùng ví dụ gần gũi với trẻ em Tày/Nùng vùng cao
    (núi rừng, nương rẫy, lễ hội dân tộc).
    Trả về JSON: {objectives: [...], activities: [...], exercises: [...]}"
5. Auto-save to lesson_plans table (record rag_used flag)
6. Return structured JSON to frontend
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/teacher/lesson` | Generate + auto-save lesson plan |
| `GET` | `/teacher/lessons` | Fetch history; query params: `?grade=3&subject=Toán` |

### Files Changed

| File | Change |
|------|--------|
| `backend/routers/teacher.py` | RAG search before Gemini; Tày/Nùng prompt; return JSON; add GET /lessons |
| `backend/services/vector_search.py` | Reuse existing search function — no changes needed |
| `frontend/app/(protected)/teacher/page.tsx` | 2-column layout, section cards renderer, history panel + filters |
| `frontend/lib/api.ts` | Add `fetchLessonHistory()`; update `generateLesson()` return type |

---

## Section 3: Data Model

### Migration: 005_lesson_plans.sql

```sql
create table lesson_plans (
  id         uuid    primary key default gen_random_uuid(),
  user_id    uuid    references profiles on delete cascade,
  topic      text    not null,
  grade      int     not null,
  subject    text    not null,
  objectives text[],
  activities jsonb,   -- [{step: int, duration: string, description: string}]
  exercises  text[],
  rag_used   boolean default false,
  created_at timestamptz default now()
);

alter table lesson_plans enable row level security;

create policy "Teachers manage own lesson plans"
  on lesson_plans for all using (auth.uid() = user_id);
```

`rag_used` is a debug/analytics flag — lets us compare quality of RAG vs fallback responses over time.

---

## Out of Scope (this branch)

- Lesson plan export (print / download) — can add later as Section C option
- Sharing lesson plans between teachers
- Subjects other than Toán in Qdrant (Tiếng Việt, TNXH, Khoa học) — will fallback to Gemini until data is ingested
- Student-facing lesson plan view

---

## Implementation Order

1. Create branch `feature/teacher-rbac-lesson-plans`
2. DB migration: `005_lesson_plans.sql`
3. `middleware.ts` — RBAC enforcement
4. `auth/actions.ts` — role-based redirect
5. `(protected)/layout.tsx` + `ProtectedShell.tsx` — role-aware nav
6. `backend/routers/teacher.py` — RAG + structured JSON + history endpoint
7. `frontend/app/(protected)/teacher/page.tsx` — new UI
8. `frontend/lib/api.ts` — updated API calls
