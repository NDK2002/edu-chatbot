import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

async function proxy(req: NextRequest): Promise<NextResponse> {
  const forwardHeaders: Record<string, string> = {
    "content-type": req.headers.get("content-type") ?? "application/json",
    "x-forwarded-for":
      req.headers.get("x-forwarded-for") ?? req.headers.get("x-real-ip") ?? "unknown",
  };
  const auth = req.headers.get("authorization");
  if (auth) forwardHeaders["authorization"] = auth;

  const body = req.method !== "GET" ? await req.text() : undefined;

  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}/conversations`, {
      method: req.method,
      headers: forwardHeaders,
      body,
    });
  } catch {
    return NextResponse.json({ message: "Không thể kết nối tới máy chủ." }, { status: 503 });
  }

  const resBody = await res.text();
  return new NextResponse(resBody, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}

export const GET = proxy;
export const POST = proxy;
