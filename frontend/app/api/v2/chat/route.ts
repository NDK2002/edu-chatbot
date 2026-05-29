import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest): Promise<NextResponse> {
  const clientIp =
    req.headers.get("x-forwarded-for") ??
    req.headers.get("x-real-ip") ??
    "unknown";

  const forwardHeaders: Record<string, string> = {
    "content-type": req.headers.get("content-type") ?? "application/json",
    cookie: req.headers.get("cookie") ?? "",
    "x-forwarded-for": clientIp,
  };
  const auth = req.headers.get("authorization");
  if (auth) forwardHeaders["authorization"] = auth;

  let fastapiRes: Response;
  try {
    fastapiRes = await fetch(`${BACKEND_URL}/v2/chat/`, {
      method: "POST",
      headers: forwardHeaders,
      body: await req.text(),
    });
  } catch {
    return NextResponse.json(
      { message: "Không thể kết nối tới máy chủ AI. Vui lòng thử lại sau." },
      { status: 503 }
    );
  }

  // Non-2xx (e.g. 429 rate limit, 400, 500) — buffer and forward as JSON
  if (!fastapiRes.ok) {
    const body = await fastapiRes.text();
    const res = new NextResponse(body, {
      status: fastapiRes.status,
      headers: {
        "content-type":
          fastapiRes.headers.get("content-type") ?? "application/json",
      },
    });
    for (const [key, value] of fastapiRes.headers.entries()) {
      if (key.startsWith("x-ratelimit")) res.headers.set(key, value);
    }
    return res;
  }

  // Forward SSE stream directly — do NOT buffer with .text()
  return new NextResponse(fastapiRes.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
}
