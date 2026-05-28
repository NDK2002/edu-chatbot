import { type NextRequest, NextResponse } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";

const PROTECTED_PREFIXES = ["/student", "/teacher", "/dictionary", "/chat"];
const AUTH_PREFIXES = ["/login", "/register"];

export default async function proxy(request: NextRequest) {
  const start = Date.now();
  const { supabaseResponse, user } = await updateSession(request);
  const { pathname } = request.nextUrl;

  const isProtected = PROTECTED_PREFIXES.some((p) => pathname.startsWith(p));
  const isAuthPage = AUTH_PREFIXES.some((p) => pathname.startsWith(p));

  let response: NextResponse;

  if (isProtected && !user) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    response = NextResponse.redirect(url);
  } else if (isAuthPage && user) {
    const url = request.nextUrl.clone();
    url.pathname = "/student";
    response = NextResponse.redirect(url);
  } else {
    response = supabaseResponse;
  }

  const latency = Date.now() - start;
  const now = new Date();
  const timestamp = `${now.getFullYear()}/${String(now.getMonth() + 1).padStart(2, "0")}/${String(now.getDate()).padStart(2, "0")} ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;
  const ip =
    request.headers.get("x-forwarded-for")?.split(",")[0].trim() ??
    request.headers.get("x-real-ip") ??
    "unknown";
  console.log(`[ACCESS] ${timestamp} ${ip} ${request.method} ${pathname} ${response.status} ${latency}ms`);

  return response;
}

export const config = {
  matcher: [
    // Skip Next.js internals, static files, images
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
