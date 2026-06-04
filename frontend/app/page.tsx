import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export default async function Home() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  const role = data.user?.user_metadata?.role;
  if (role === "teacher") redirect("/teacher");
  redirect("/student");
}
