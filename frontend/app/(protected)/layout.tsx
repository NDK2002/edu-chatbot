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
