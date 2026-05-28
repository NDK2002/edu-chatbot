"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

// Học sinh dân tộc thiểu số thường không có email.
// Username được map sang synthetic email nội bộ để dùng với Supabase Auth.
// Domain này không cần tồn tại thật — email confirmation phải TẮT trong Supabase dashboard.
const SYNTHETIC_DOMAIN = "edu-chatbot.local";

function toEmail(username: string): string {
  return `${username}@${SYNTHETIC_DOMAIN}`;
}

function sanitizeUsername(raw: string): string {
  return raw.toLowerCase().trim().replace(/[^a-z0-9_]/g, "").slice(0, 20);
}

export async function login(_prevState: unknown, formData: FormData) {
  const supabase = await createClient();
  const username = sanitizeUsername(formData.get("username") as string);

  if (username.length < 3) return { error: "Tên đăng nhập không hợp lệ" };

  const { error } = await supabase.auth.signInWithPassword({
    email: toEmail(username),
    password: formData.get("password") as string,
  });

  if (error) return { error: error.message };
  redirect("/chat");
}

export async function register(_prevState: unknown, formData: FormData) {
  const supabase = await createClient();
  const username = sanitizeUsername(formData.get("username") as string);

  if (username.length < 3) return { error: "Tên đăng nhập phải có ít nhất 3 ký tự" };

  const role = formData.get("role") as "student" | "teacher";
  const gradeRaw = formData.get("grade");
  const metadata: Record<string, unknown> = {
    username,
    display_name: (formData.get("display_name") as string).trim(),
    role,
  };
  if (role === "student" && gradeRaw) {
    metadata.grade = Number(gradeRaw);
  }

  const { error } = await supabase.auth.signUp({
    email: toEmail(username),
    password: formData.get("password") as string,
    options: { data: metadata },
  });

  if (error) return { error: error.message };
  redirect("/chat");
}

export async function logout() {
  const supabase = await createClient();
  await supabase.auth.signOut();
  redirect("/login");
}
