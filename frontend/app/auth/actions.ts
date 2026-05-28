"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export async function login(_prevState: unknown, formData: FormData) {
  const supabase = await createClient();

  const { error } = await supabase.auth.signInWithPassword({
    email: formData.get("email") as string,
    password: formData.get("password") as string,
  });

  if (error) return { error: error.message };

  redirect("/chat");
}

export async function register(_prevState: unknown, formData: FormData) {
  const supabase = await createClient();

  const role = formData.get("role") as "student" | "teacher";
  const gradeRaw = formData.get("grade");
  const metadata: Record<string, unknown> = {
    display_name: formData.get("display_name") as string,
    role,
  };
  if (role === "student" && gradeRaw) {
    metadata.grade = Number(gradeRaw);
  }

  const { error } = await supabase.auth.signUp({
    email: formData.get("email") as string,
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
