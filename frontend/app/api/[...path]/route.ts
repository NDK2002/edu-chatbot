import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

async function proxy(req: NextRequest): Promise<NextResponse> {
  const backendPath = req.nextUrl.pathname.replace(/^\/api/, "");
  const targetUrl = `${BACKEND_URL}${backendPath}${req.nextUrl.search}`;

  const clientIp =
    req.headers.get("x-forwarded-for") ??
    req.headers.get("x-real-ip") ??
    "unknown";

  const body =
    req.method !== "GET" && req.method !== "HEAD"
      ? await req.text()
      : undefined;

  let fastapiRes: Response;
  try {
    fastapiRes = await fetch(targetUrl, {
      method: req.method,
      headers: {
        "content-type": req.headers.get("content-type") ?? "application/json",
        cookie: req.headers.get("cookie") ?? "",
        "x-forwarded-for": clientIp,
      },
      body,
    });
  } catch {
    return NextResponse.json(
      { message: "Không thể kết nối tới máy chủ AI. Vui lòng thử lại sau." },
      { status: 503 }
    );
  }

  const resBody = await fastapiRes.text();
  const nextRes = new NextResponse(resBody, {
    status: fastapiRes.status,
    headers: {
      "content-type":
        fastapiRes.headers.get("content-type") ?? "application/json",
    },
  });

  const setCookie = fastapiRes.headers.get("set-cookie");
  if (setCookie) {
    nextRes.headers.set("set-cookie", setCookie);
  }

  for (const [key, value] of fastapiRes.headers.entries()) {
    if (key.startsWith("x-ratelimit")) {
      nextRes.headers.set(key, value);
    }
  }

  return nextRes;
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const PATCH = proxy;
