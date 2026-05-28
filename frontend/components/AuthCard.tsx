"use client";

import { useActionState, useState } from "react";
import { login, register } from "@/app/auth/actions";

type Mode = "login" | "register";
type Role = "student" | "teacher";
type AnimPhase =
  | "idle"
  | "exit-left"
  | "exit-right"
  | "enter-left"
  | "enter-right";

const ANIM_CLASS: Record<AnimPhase, string> = {
  idle: "",
  "exit-left": "animate-slide-exit-left",
  "exit-right": "animate-slide-exit-right",
  "enter-left": "animate-slide-enter-left",
  "enter-right": "animate-slide-enter-right",
};

export default function AuthCard({ initialMode }: { initialMode: Mode }) {
  const [mode, setMode] = useState<Mode>(initialMode);
  const [anim, setAnim] = useState<AnimPhase>("idle");
  const [role, setRole] = useState<Role>("student");

  const [loginState, loginAction, isLoginPending] = useActionState(
    login,
    undefined
  );
  const [registerState, registerAction, isRegisterPending] = useActionState(
    register,
    undefined
  );

  const switchMode = (next: Mode) => {
    if (next === mode || anim !== "idle") return;
    const forward = next === "register";
    setAnim(forward ? "exit-left" : "exit-right");
    setTimeout(() => {
      setMode(next);
      window.history.replaceState(null, "", `/${next}`);
      setAnim(forward ? "enter-right" : "enter-left");
      setTimeout(() => setAnim("idle"), 260);
    }, 190);
  };

  const isLogin = mode === "login";
  const isPending = isLogin ? isLoginPending : isRegisterPending;

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-sky-50 to-indigo-50 px-4 py-8">
      <div className="w-full max-w-sm">
        {/* Logo — fade-in once on load */}
        <div className="text-center mb-8 animate-page-in">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-sky-400 to-indigo-500 flex items-center justify-center shadow-lg mx-auto mb-3 text-2xl select-none">
            📚
          </div>
          <h1 className="text-xl font-bold text-sky-800">Chatbot Giáo dục</h1>
          <p className="text-sm text-sky-500 mt-1">Việt–Tày/Nùng · Lớp 1–5</p>
        </div>

        {/* Card */}
        <div className={`bg-white rounded-2xl shadow-sm border border-gray-100 p-6 ${ANIM_CLASS[anim]}`}>
          {/* Tab switcher */}
          <div className="flex gap-1 mb-5 bg-gray-100 rounded-xl p-1">
            <TabButton
              active={isLogin}
              onClick={() => switchMode("login")}
              label="Đăng nhập"
            />
            <TabButton
              active={!isLogin}
              onClick={() => switchMode("register")}
              label="Đăng ký"
            />
          </div>

          {/* Forms — conditionally rendered so DOM updates when mode switches */}
          {isLogin ? (
            <form action={loginAction} className="space-y-4">
              <Field label="Tên đăng nhập">
                <input
                  name="username"
                  type="text"
                  required
                  autoComplete="username"
                  placeholder="vd: khang.nd"
                  className={inputCls}
                />
              </Field>

              <Field label="Mật khẩu">
                <input
                  name="password"
                  type="password"
                  required
                  autoComplete="current-password"
                  placeholder="••••••••"
                  className={inputCls}
                />
              </Field>

              {loginState?.error && (
                <ErrorBox msg={translateLoginError(loginState.error)} />
              )}

              <SubmitButton pending={isPending} label="Đăng nhập" pendingLabel="Đang đăng nhập..." />
            </form>
          ) : (
            <form action={registerAction} className="space-y-4">
              <Field label="Tên hiển thị">
                <input
                  name="display_name"
                  type="text"
                  required
                  autoComplete="name"
                  placeholder="Ví dụ: Khang Nguyễn"
                  className={inputCls}
                />
              </Field>

              <Field label="Tên đăng nhập">
                <input
                  name="username"
                  type="text"
                  required
                  autoComplete="username"
                  placeholder="vd: khang.nd"
                  className={inputCls}
                />
              </Field>

              <Field label="Mật khẩu">
                <input
                  name="password"
                  type="password"
                  required
                  minLength={6}
                  autoComplete="new-password"
                  placeholder="Ít nhất 6 ký tự"
                  className={inputCls}
                />
              </Field>

              {/* Role picker */}
              <input type="hidden" name="role" value={role} />
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Bạn là
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {ROLES.map(({ value, emoji, label }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setRole(value)}
                      className={`flex items-center gap-2 px-3 py-2.5 rounded-xl border text-sm font-medium transition-colors ${
                        role === value
                          ? "border-sky-400 bg-sky-50 text-sky-700"
                          : "border-gray-200 bg-gray-50 text-gray-600 hover:border-sky-200"
                      }`}
                    >
                      <span className="text-base">{emoji}</span>
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {role === "student" && (
                <Field label="Đang học lớp">
                  <select name="grade" className={inputCls}>
                    {[1, 2, 3, 4, 5].map((g) => (
                      <option key={g} value={g}>
                        Lớp {g}
                      </option>
                    ))}
                  </select>
                </Field>
              )}

              {registerState?.error && (
                <ErrorBox msg={translateRegisterError(registerState.error)} />
              )}

              <SubmitButton pending={isPending} label="Tạo tài khoản" pendingLabel="Đang tạo tài khoản..." />
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Small helpers ────────────────────────────────────────────────────── */

const inputCls =
  "w-full px-3.5 py-2.5 rounded-xl border border-gray-200 bg-gray-50 text-sm focus:outline-none focus:ring-2 focus:ring-sky-300 focus:border-sky-300 transition-shadow";

const ROLES: { value: Role; emoji: string; label: string }[] = [
  { value: "student", emoji: "🧒", label: "Học sinh" },
  { value: "teacher", emoji: "👩‍🏫", label: "Giáo viên" },
];

function TabButton({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 ${
        active
          ? "bg-white shadow-sm text-sky-700"
          : "text-gray-500 hover:text-gray-700"
      }`}
    >
      {label}
    </button>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1.5">
        {label}
      </label>
      {children}
    </div>
  );
}

function ErrorBox({ msg }: { msg: string }) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-xl px-3.5 py-2.5 text-sm text-red-700 animate-page-in">
      {msg}
    </div>
  );
}

function SubmitButton({
  pending,
  label,
  pendingLabel,
}: {
  pending: boolean;
  label: string;
  pendingLabel: string;
}) {
  return (
    <button
      type="submit"
      disabled={pending}
      className="w-full py-2.5 rounded-xl bg-sky-500 text-white text-sm font-medium hover:bg-sky-600 active:scale-[0.99] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {pending ? pendingLabel : label}
    </button>
  );
}

function translateLoginError(msg: string): string {
  if (msg.includes("Invalid login credentials")) return "Sai tên đăng nhập hoặc mật khẩu.";
  if (msg.includes("Too many requests")) return "Quá nhiều lần thử. Vui lòng đợi vài phút.";
  return "Đã có lỗi xảy ra. Vui lòng thử lại.";
}

function translateRegisterError(msg: string): string {
  if (msg === "EMAIL_CONFIRM_STILL_ON")
    return "Cần tắt \"Confirm email\" trong Supabase dashboard (Authentication → Policies) rồi thử lại.";
  if (msg.includes("User already registered") || msg.includes("already been registered"))
    return "Tên đăng nhập này đã có người dùng rồi.";
  if (msg.includes("Password should be at least") || msg.includes("weak"))
    return "Mật khẩu phải có ít nhất 6 ký tự, gồm chữ hoa, chữ thường, số và ký tự đặc biệt (vd: Abc@123).";
  if (msg.includes("Too many requests")) return "Quá nhiều lần thử. Vui lòng đợi vài phút.";
  if (msg.includes("Database error")) return "Lỗi hệ thống. Vui lòng liên hệ quản trị viên.";
  return "Đã có lỗi xảy ra. Vui lòng thử lại.";
}
