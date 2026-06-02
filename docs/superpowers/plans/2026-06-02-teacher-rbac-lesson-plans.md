# Teacher RBAC + RAG Lesson Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add role-based access control (teacher/student) and upgrade the teacher lesson plan feature with RAG-augmented generation, structured section cards, and filterable lesson history.

**Architecture:** A new `frontend/middleware.ts` (replacing the inactive `proxy.ts`) enforces RBAC at the edge — it reads `user.user_metadata.role` from the Supabase JWT and blocks students from `/teacher`. The FastAPI teacher router is rewritten to search Qdrant before calling Gemini (JSON mode), auto-saving results to a new `lesson_plans` Supabase table. The teacher page becomes a 2-column layout with section cards and a filterable history panel.

**Tech Stack:** Next.js 15 App Router, `@supabase/ssr` middleware, FastAPI, supabase-py (service role), Qdrant (`vector_search.search()`), Google Gemini (`response_mime_type="application/json"`)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `frontend/middleware.ts` | **Create** | RBAC: block `/teacher` for students, role-based redirect after auth |
| `frontend/proxy.ts` | **Delete** | Dead code — replaced by `middleware.ts` |
| `frontend/app/auth/actions.ts` | **Modify** | Redirect to `/teacher` or `/student` based on role after login/register |
| `frontend/app/(protected)/layout.tsx` | **Modify** | Read `role` from `user_metadata`, pass to `ProtectedShell` |
| `frontend/components/ProtectedShell.tsx` | **Modify** | Conditionally render teacher nav item; accept `role` prop |
| `frontend/lib/api.ts` | **Modify** | Add `LessonActivity`, `LessonPlanResponse`, `LessonHistoryItem` types; add `fetchLessonHistory()`; update `generateLesson()` with auth header + new return type |
| `frontend/app/(protected)/teacher/page.tsx` | **Rewrite** | 2-column layout, section cards renderer, history panel + filters, mobile toggle |
| `backend/services/gemini.py` | **Modify** | Add `ask_gemini_json()` — Gemini with `response_mime_type="application/json"` |
| `backend/routers/teacher.py` | **Rewrite** | RAG search → Gemini JSON → save to Supabase; `GET /teacher/lessons` with filters |
| `supabase/migrations/005_lesson_plans.sql` | **Create** | `lesson_plans` table + RLS policy |

---

## Task 1: Create branch and DB migration

**Files:**
- Create: `supabase/migrations/005_lesson_plans.sql`

- [ ] **Step 1: Create the feature branch**

```bash
git checkout main
git pull origin main
git checkout -b feature/teacher-rbac-lesson-plans
```

- [ ] **Step 2: Write migration file**

Create `supabase/migrations/005_lesson_plans.sql`:

```sql
create table lesson_plans (
  id         uuid    primary key default gen_random_uuid(),
  user_id    uuid    references profiles on delete cascade,
  topic      text    not null,
  grade      int     not null,
  subject    text    not null,
  objectives text[],
  activities jsonb,
  exercises  text[],
  rag_used   boolean default false,
  created_at timestamptz default now()
);

alter table lesson_plans enable row level security;

create policy "Teachers manage own lesson plans"
  on lesson_plans for all using (auth.uid() = user_id);
```

- [ ] **Step 3: Apply migration**

Run in Supabase SQL editor (dashboard → SQL editor → paste and run), or:
```bash
supabase db push
```

- [ ] **Step 4: Verify table exists**

In Supabase Table Editor, confirm `lesson_plans` appears with columns: `id`, `user_id`, `topic`, `grade`, `subject`, `objectives`, `activities`, `exercises`, `rag_used`, `created_at`.

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/005_lesson_plans.sql
git commit -m "feat: add lesson_plans table with RLS"
```

---

## Task 2: RBAC Middleware

**Files:**
- Create: `frontend/middleware.ts`
- Delete: `frontend/proxy.ts`

`proxy.ts` currently exists but is NOT active as Next.js middleware (wrong filename). Create `middleware.ts` with the same base logic plus role checks.

- [ ] **Step 1: Create `frontend/middleware.ts`**

```typescript
import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";

const PROTECTED_PREFIXES = ["/student", "/teacher", "/dictionary", "/chat"];
const AUTH_PREFIXES = ["/login", "/register"];

function cloneWithRedirect(
  request: NextRequest,
  pathname: string,
  base: NextResponse,
): NextResponse {
  const url = request.nextUrl.clone();
  url.pathname = pathname;
  const res = NextResponse.redirect(url);
  // Preserve Supabase session cookie updates
  base.cookies.getAll().forEach((c) => res.cookies.set(c.name, c.value));
  return res;
}

export default async function middleware(request: NextRequest) {
  const { supabaseResponse, user } = await updateSession(request);
  const { pathname } = request.nextUrl;

  const isProtected = PROTECTED_PREFIXES.some((p) => pathname.startsWith(p));
  const isAuthPage = AUTH_PREFIXES.some((p) => pathname.startsWith(p));
  const role = (user?.user_metadata?.role as string) ?? "student";

  // Unauthenticated on protected route → /login
  if (isProtected && !user) {
    return cloneWithRedirect(request, "/login", supabaseResponse);
  }

  // Student blocked from /teacher → /student
  if (user && role === "student" && pathname.startsWith("/teacher")) {
    return cloneWithRedirect(request, "/student", supabaseResponse);
  }

  // Logged-in user on auth page → role-based home
  if (isAuthPage && user) {
    return cloneWithRedirect(
      request,
      role === "teacher" ? "/teacher" : "/student",
      supabaseResponse,
    );
  }

  const ip =
    request.headers.get("x-forwarded-for")?.split(",")[0].trim() ??
    request.headers.get("x-real-ip") ??
    "unknown";
  const now = new Date();
  const ts = `${now.getFullYear()}/${String(now.getMonth() + 1).padStart(2, "0")}/${String(now.getDate()).padStart(2, "0")} ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;
  console.log(`[ACCESS] ${ts} ${ip} ${request.method} ${pathname} ${supabaseResponse.status}`);

  return supabaseResponse;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
```

- [ ] **Step 2: Delete `frontend/proxy.ts`**

```bash
git rm frontend/proxy.ts
```

- [ ] **Step 3: Manual test**

Start the dev server (`cd frontend && npm run dev`). Open an incognito window.

| Action | Expected |
|--------|----------|
| Visit `http://localhost:3000/student` without login | Redirect to `/login` |
| Visit `http://localhost:3000/teacher` without login | Redirect to `/login` |
| Log in as a student account | Redirect to `/student` |
| Manually visit `http://localhost:3000/teacher` as student | Redirect to `/student` |

- [ ] **Step 4: Commit**

```bash
git add frontend/middleware.ts
git commit -m "feat: add RBAC middleware — block /teacher for students"
```

---

## Task 3: Role-based redirect after login/register

**Files:**
- Modify: `frontend/app/auth/actions.ts`

- [ ] **Step 1: Update `login` action**

In `frontend/app/auth/actions.ts`, replace the last two lines of `login`:

```typescript
// BEFORE:
if (error) return { error: error.message };
redirect("/student");

// AFTER:
if (error) return { error: error.message };
const { data: { user } } = await supabase.auth.getUser();
const role = user?.user_metadata?.role ?? "student";
redirect(role === "teacher" ? "/teacher" : "/student");
```

- [ ] **Step 2: Update `register` action**

In the same file, replace the last line of `register`:

```typescript
// BEFORE:
redirect("/student");

// AFTER:
redirect(role === "teacher" ? "/teacher" : "/student");
```

The `role` variable is already declared earlier in `register` from `formData.get("role")`.

- [ ] **Step 3: Manual test**

Register a new teacher account → should land on `/teacher`. Register a student account → should land on `/student`. Log out and log in as teacher again → should land on `/teacher`.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/auth/actions.ts
git commit -m "feat: redirect to /teacher or /student based on role after auth"
```

---

## Task 4: Role-aware navigation

**Files:**
- Modify: `frontend/app/(protected)/layout.tsx`
- Modify: `frontend/components/ProtectedShell.tsx`

- [ ] **Step 1: Pass `role` from layout**

Replace the entire content of `frontend/app/(protected)/layout.tsx`:

```typescript
import { createClient } from "@/lib/supabase/server";
import ProtectedShell from "@/components/ProtectedShell";

export default async function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  const meta = data.user?.user_metadata;
  const displayName: string | null = meta?.display_name ?? meta?.username ?? null;
  const role: "student" | "teacher" = (meta?.role === "teacher") ? "teacher" : "student";
  return <ProtectedShell displayName={displayName} role={role}>{children}</ProtectedShell>;
}
```

- [ ] **Step 2: Update `ProtectedShell` props interface**

In `frontend/components/ProtectedShell.tsx`, update the props type:

```typescript
// BEFORE:
export default function ProtectedShell({
  children,
  displayName,
}: {
  children: React.ReactNode;
  displayName: string | null;
}) {

// AFTER:
export default function ProtectedShell({
  children,
  displayName,
  role = "student",
}: {
  children: React.ReactNode;
  displayName: string | null;
  role?: "student" | "teacher";
}) {
```

- [ ] **Step 3: Make teacher nav item conditional**

In `ProtectedShell.tsx`, the `MOBILE_NAV` constant currently hardcodes all three tabs. Replace the constant and the nav render with role-aware logic.

Find the `MOBILE_NAV` array declaration and replace through the end of the component (the nav JSX), applying this change:

```typescript
// BEFORE (at top of file):
const MOBILE_NAV = [
  { href: "/student", ... },
  { href: "/dictionary", ... },
  { href: "/teacher", ... },  // always shown
];

// AFTER — split into base + teacher item:
const MOBILE_NAV_BASE = [
  {
    href: "/student",
    short: "Chat",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 0 1-.825-.242m9.345-8.334a2.126 2.126 0 0 0-.476-.095 48.64 48.64 0 0 0-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0 0 11.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
      </svg>
    ),
  },
  {
    href: "/dictionary",
    short: "Từ điển",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
      </svg>
    ),
  },
];

const TEACHER_NAV_ITEM = {
  href: "/teacher",
  short: "Soạn bài",
  icon: (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4.26 10.147a60.438 60.438 0 0 0-.491 6.347A48.62 48.62 0 0 1 12 20.904a48.62 48.62 0 0 1 8.232-4.41 60.46 60.46 0 0 0-.491-6.347m-15.482 0a50.636 50.636 0 0 0-2.658-.813A59.906 59.906 0 0 1 12 3.493a59.903 59.903 0 0 1 10.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0 1 12 13.489a50.702 50.702 0 0 1 3.741-3.342M6.75 15a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Zm0 0v-3.675A55.378 55.378 0 0 1 12 8.443m-7.007 11.55A5.981 5.981 0 0 0 6.75 15.75v-1.5" />
    </svg>
  ),
};
```

Then inside the component body, before the return, add:

```typescript
const mobileNav = role === "teacher"
  ? [...MOBILE_NAV_BASE, TEACHER_NAV_ITEM]
  : MOBILE_NAV_BASE;
```

And update the nav map from `MOBILE_NAV.map(...)` to `mobileNav.map(...)`.

- [ ] **Step 4: Manual test**

Log in as student → teacher tab NOT in bottom nav. Log in as teacher → "Soạn bài" tab visible.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/(protected)/layout.tsx frontend/components/ProtectedShell.tsx
git commit -m "feat: role-aware nav — hide Soạn bài tab for students"
```

---

## Task 5: Gemini JSON helper

**Files:**
- Modify: `backend/services/gemini.py`

- [ ] **Step 1: Create tests directory**

```bash
mkdir -p backend/tests
touch backend/tests/__init__.py
```

- [ ] **Step 2: Write a failing test**

Create `backend/tests/test_gemini_json.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.gemini import ask_gemini_json


@pytest.mark.asyncio
async def test_ask_gemini_json_returns_string():
    mock_response = MagicMock()
    mock_response.text = '{"objectives": ["test"], "activities": [], "exercises": []}'

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("backend.services.gemini._get_client", return_value=mock_client):
        result = await ask_gemini_json("soạn giáo án bảng nhân 3", role="teacher")

    assert isinstance(result, str)
    import json
    parsed = json.loads(result)
    assert "objectives" in parsed
```

- [ ] **Step 3: Run test — expect FAIL**

```bash
cd backend
python -m pytest tests/test_gemini_json.py -v
```

Expected: `ImportError: cannot import name 'ask_gemini_json'`

- [ ] **Step 4: Add `ask_gemini_json` to `backend/services/gemini.py`**

Append after the `stream_gemini` function:

```python
async def ask_gemini_json(prompt: str, role: str = "teacher") -> str:
    """
    Gọi Gemini với response_mime_type='application/json'.
    Trả raw JSON string. Không cache — lesson plan mỗi lần khác nhau.
    """
    client = _get_client()
    for model in FALLBACK_MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=get_system_prompt(role),
                    response_mime_type="application/json",
                    max_output_tokens=2048,
                    temperature=0.3,
                ),
            )
            return response.text
        except ServerError as e:
            if e.code == 503:
                log.warning("[GEMINI] Model %s unavailable (503), trying next...", model)
                continue
            raise
    raise HTTPException(status_code=503, detail="AI_UNAVAILABLE")
```

- [ ] **Step 5: Run test — expect PASS**

```bash
python -m pytest tests/test_gemini_json.py -v
```

Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add backend/services/gemini.py backend/tests/__init__.py backend/tests/test_gemini_json.py
git commit -m "feat: add ask_gemini_json for structured Gemini output"
```

---

## Task 6: Rewrite teacher router — RAG + JSON + history

**Files:**
- Rewrite: `backend/routers/teacher.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_teacher.py`:

```python
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

MOCK_PLAN = {
    "objectives": ["Học sinh thuộc bảng nhân 3"],
    "activities": [{"step": 1, "duration": "5 phút", "description": "Khởi động"}],
    "exercises": ["3 × 4 = ?"],
}

@pytest.mark.asyncio
async def test_generate_lesson_no_auth_returns_plan():
    """No auth header → plan generated but not saved (lesson_id=None)."""
    with patch("backend.routers.teacher.search", new_callable=AsyncMock) as mock_search, \
         patch("backend.routers.teacher.ask_gemini_json", new_callable=AsyncMock) as mock_gemini:
        mock_search.return_value = {"retrieval_status": "no_relevant_context", "context": []}
        mock_gemini.return_value = json.dumps(MOCK_PLAN)

        res = client.post("/teacher/lesson", json={"topic": "Bảng nhân 3", "grade": 3, "subject": "Toán"})

    assert res.status_code == 200
    data = res.json()
    assert data["objectives"] == MOCK_PLAN["objectives"]
    assert data["rag_used"] is False
    assert data["id"] is None


@pytest.mark.asyncio
async def test_generate_lesson_with_rag_context():
    """When Qdrant returns strong context, rag_used=True."""
    with patch("backend.routers.teacher.search", new_callable=AsyncMock) as mock_search, \
         patch("backend.routers.teacher.ask_gemini_json", new_callable=AsyncMock) as mock_gemini:
        mock_search.return_value = {
            "retrieval_status": "strong_context",
            "context": [{"content": "Bảng nhân 3: 3×1=3, 3×2=6..."}],
        }
        mock_gemini.return_value = json.dumps(MOCK_PLAN)

        res = client.post("/teacher/lesson", json={"topic": "Bảng nhân 3", "grade": 3, "subject": "Toán"})

    assert res.status_code == 200
    assert res.json()["rag_used"] is True


def test_list_lessons_requires_auth():
    res = client.get("/teacher/lessons")
    assert res.status_code == 401
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
python -m pytest tests/test_teacher.py -v
```

Expected: failures — endpoints have wrong signatures/return types.

- [ ] **Step 3: Rewrite `backend/routers/teacher.py`**

```python
import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from backend.services.gemini import ask_gemini_json
from backend.services.supabase_client import get_supabase, verify_jwt
from backend.services.vector_search import search

log = logging.getLogger(__name__)
router = APIRouter()


class LessonRequest(BaseModel):
    topic: str
    grade: int = 3
    subject: str = "Toán"


class LessonResponse(BaseModel):
    id: Optional[str] = None
    topic: str
    grade: int
    subject: str
    objectives: list[str]
    activities: list[dict]
    exercises: list[str]
    rag_used: bool


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _save_lesson_sync(
    user_id: str,
    topic: str,
    grade: int,
    subject: str,
    objectives: list,
    activities: list,
    exercises: list,
    rag_used: bool,
) -> str:
    sb = get_supabase()
    if sb is None:
        raise RuntimeError("Supabase not configured")
    resp = (
        sb.table("lesson_plans")
        .insert({
            "user_id": user_id,
            "topic": topic,
            "grade": grade,
            "subject": subject,
            "objectives": objectives,
            "activities": activities,
            "exercises": exercises,
            "rag_used": rag_used,
        })
        .execute()
    )
    return resp.data[0]["id"]


def _list_lessons_sync(
    user_id: str,
    grade: Optional[int],
    subject: Optional[str],
) -> list[dict]:
    sb = get_supabase()
    if sb is None:
        return []
    query = (
        sb.table("lesson_plans")
        .select("id, topic, grade, subject, objectives, activities, exercises, rag_used, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
    )
    if grade is not None:
        query = query.eq("grade", grade)
    if subject:
        query = query.eq("subject", subject)
    return query.execute().data or []


@router.post("/lesson", response_model=LessonResponse)
async def generate_lesson(
    req: LessonRequest,
    authorization: Optional[str] = Header(None),
):
    # 1. RAG search (grade=0 → no grade filter, search all lớp 1–5)
    rag_result = await search(req.topic, grade=0, top_k=40)
    rag_context = ""
    rag_used = False
    if rag_result and rag_result.get("retrieval_status") in ("strong_context", "medium_context"):
        contexts = rag_result.get("context", [])
        if contexts:
            rag_context = "\n\n".join(c["content"] for c in contexts[:3])
            rag_used = True

    # 2. Build prompt
    json_schema = (
        '{"objectives": ["chuỗi mục tiêu"], '
        '"activities": [{"step": 1, "duration": "5 phút", "description": "mô tả"}], '
        '"exercises": ["bài tập"]}'
    )
    base_instruction = (
        f"Soạn giáo án môn {req.subject} lớp {req.grade}, chủ đề: {req.topic}. "
        f"Dùng ví dụ gần gũi với học sinh Tày/Nùng vùng cao (núi rừng, nương rẫy, lễ hội dân tộc). "
        f"Chuẩn kiến thức theo GDPT 2018. "
        f"Trả về JSON đúng format: {json_schema}"
    )
    if rag_context:
        prompt = (
            f"Dưới đây là nội dung từ SGK Cánh Diều lớp {req.grade}:\n{rag_context}\n\n"
            f"Dựa trên nội dung trên, {base_instruction}"
        )
    else:
        prompt = base_instruction

    # 3. Gemini JSON
    json_text = await ask_gemini_json(prompt, role="teacher")
    json_text = _strip_json_fence(json_text)
    try:
        plan = json.loads(json_text)
    except json.JSONDecodeError:
        log.error("[TEACHER] Invalid JSON from Gemini: %.200s", json_text)
        raise HTTPException(status_code=500, detail="AI trả về định dạng không hợp lệ")

    objectives = plan.get("objectives", [])
    activities = plan.get("activities", [])
    exercises = plan.get("exercises", [])

    # 4. Save to Supabase (best-effort — don't fail generation if save fails)
    lesson_id = None
    if authorization:
        token = authorization.removeprefix("Bearer ").strip()
        try:
            user_id = await verify_jwt(token)
            lesson_id = await asyncio.to_thread(
                _save_lesson_sync, user_id, req.topic, req.grade, req.subject,
                objectives, activities, exercises, rag_used,
            )
        except Exception as e:
            log.warning("[TEACHER] Save lesson failed: %s", e)

    return LessonResponse(
        id=lesson_id,
        topic=req.topic,
        grade=req.grade,
        subject=req.subject,
        objectives=objectives,
        activities=activities,
        exercises=exercises,
        rag_used=rag_used,
    )


@router.get("/lessons")
async def list_lessons(
    grade: Optional[int] = Query(None),
    subject: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
    token = authorization.removeprefix("Bearer ").strip()
    user_id = await verify_jwt(token)
    lessons = await asyncio.to_thread(_list_lessons_sync, user_id, grade, subject)
    return {"lessons": lessons}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest tests/test_teacher.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/teacher.py backend/tests/test_teacher.py
git commit -m "feat: teacher router — RAG-augmented lesson plan, JSON output, history endpoint"
```

---

## Task 7: Frontend API types and functions

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add types and update `generateLesson` + add `fetchLessonHistory`**

In `frontend/lib/api.ts`:

1. Remove the old `LessonResponse` interface.
2. Add the new types and update/add functions.

The final state of the lesson-related section of the file (everything after `streamChat`) should be:

```typescript
export interface LessonActivity {
  step: number;
  duration: string;
  description: string;
}

export interface LessonPlanResponse {
  id: string | null;
  topic: string;
  grade: number;
  subject: string;
  objectives: string[];
  activities: LessonActivity[];
  exercises: string[];
  rag_used: boolean;
}

export interface LessonHistoryItem extends LessonPlanResponse {
  id: string;
  created_at: string;
}

export async function generateLesson(
  topic: string,
  grade: number,
  subject: string
): Promise<LessonPlanResponse> {
  const token = await getAccessToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}/teacher/lesson`, {
    method: "POST",
    headers,
    body: JSON.stringify({ topic, grade, subject }),
  });
  if (!res.ok) throw new Error(`Lỗi máy chủ: ${res.status}`);
  return res.json();
}

export async function fetchLessonHistory(
  grade?: number | null,
  subject?: string | null
): Promise<LessonHistoryItem[]> {
  const token = await getAccessToken();
  if (!token) return [];

  const params = new URLSearchParams();
  if (grade) params.set("grade", grade.toString());
  if (subject) params.set("subject", subject);

  const res = await fetch(`${API_URL}/teacher/lessons?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return [];
  const data = await res.json();
  return data.lessons ?? [];
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend
npx tsc --noEmit
```

Expected: no errors related to `api.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat: add LessonPlanResponse types and fetchLessonHistory to api.ts"
```

---

## Task 8: Rewrite teacher page UI

**Files:**
- Rewrite: `frontend/app/(protected)/teacher/page.tsx`

- [ ] **Step 1: Rewrite the page**

Replace the entire file with:

```typescript
"use client";

import { useState, useEffect, useCallback } from "react";
import Image from "next/image";
import {
  generateLesson,
  fetchLessonHistory,
  type LessonPlanResponse,
  type LessonHistoryItem,
} from "@/lib/api";

const SUBJECTS = ["Toán", "Tiếng Việt", "Tự nhiên và Xã hội", "Khoa học"];
const GRADES = [1, 2, 3, 4, 5];

export default function TeacherPage() {
  const [topic, setTopic] = useState("");
  const [grade, setGrade] = useState<number>(3);
  const [subject, setSubject] = useState("Toán");
  const [result, setResult] = useState<LessonPlanResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const [history, setHistory] = useState<LessonHistoryItem[]>([]);
  const [filterGrade, setFilterGrade] = useState<number | null>(null);
  const [filterSubject, setFilterSubject] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const loadHistory = useCallback(async () => {
    const items = await fetchLessonHistory(filterGrade, filterSubject);
    setHistory(items);
  }, [filterGrade, filterSubject]);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  async function handleSubmit(e: React.SyntheticEvent) {
    e.preventDefault();
    if (!topic.trim() || isLoading) return;
    setIsLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await generateLesson(topic.trim(), grade, subject);
      setResult(res);
      await loadHistory();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsLoading(false);
    }
  }

  function loadFromHistory(item: LessonHistoryItem) {
    setResult(item);
    setTopic(item.topic);
    setGrade(item.grade);
    setSubject(item.subject);
    setShowHistory(false);
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

            {result && <LessonPlanView plan={result} />}

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
        {plan.rag_used && (
          <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-medium">
            📚 RAG từ SGK
          </span>
        )}
      </div>

      {/* Mục tiêu */}
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

      {/* Hoạt động */}
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

      {/* Bài tập */}
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
```

- [ ] **Step 2: Check TypeScript**

```bash
cd frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Manual end-to-end test**

Start backend and frontend. Log in as teacher.

| Action | Expected |
|--------|----------|
| Land on `/teacher` after login | Page loads with empty form and history panel |
| Enter "Bảng nhân 3", Lớp 3, Toán → Tạo giáo án | 3 section cards appear: Mục tiêu (green), Hoạt động (blue), Bài tập (amber) |
| If Qdrant has math data | Badge "📚 RAG từ SGK" appears |
| After generation | History panel updates with new entry |
| Click history item | Form repopulates + cards reappear |
| Filter by Lớp 3 | History filters to lớp 3 only |
| Log in as student → visit `/teacher` | Redirected to `/student`, teacher tab not visible |
| On mobile: tap "Lịch sử" button | History panel slides in over main content |

- [ ] **Step 4: Commit**

```bash
git add frontend/app/(protected)/teacher/page.tsx
git commit -m "feat: teacher page — 2-column layout, RAG section cards, filterable history"
```

---

## Task 9: Final integration check and push

- [ ] **Step 1: Run all backend tests**

```bash
cd backend
python -m pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 2: TypeScript check**

```bash
cd frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Full manual smoke test**

| Scenario | Expected |
|----------|----------|
| Student login → nav | Chat + Từ điển tabs only |
| Teacher login → nav | Chat + Từ điển + Soạn bài tabs |
| Student visits `/teacher` | Redirect to `/student` |
| Teacher generates lesson (Toán) | Section cards + history saved |
| Teacher generates lesson (Tiếng Việt) | Section cards appear (no RAG badge — no data yet) |
| Teacher filters history by Lớp | List filters correctly |
| Unauthenticated visits `/student` | Redirect to `/login` |

- [ ] **Step 4: Push branch**

```bash
git push -u origin feature/teacher-rbac-lesson-plans
```
