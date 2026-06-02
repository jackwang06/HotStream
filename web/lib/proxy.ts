import { NextResponse } from "next/server";

export function pythonBase(): string {
  return (process.env.PYTHON_API_BASE || "http://127.0.0.1:5173").replace(/\/$/, "");
}

const JSON_CT = "application/json; charset=utf-8";

function errorResponse(message: string): NextResponse {
  return NextResponse.json({ success: false, error: message }, { status: 502, headers: { "Cache-Control": "no-store" } });
}

// Forward a GET to the Python service and mirror its JSON/text response.
export async function proxyGet(path: string, search: string, timeoutMs = 20_000): Promise<NextResponse> {
  try {
    const upstream = await fetch(`${pythonBase()}${path}${search}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") || JSON_CT, "Cache-Control": "no-store" },
    });
  } catch (e) {
    return errorResponse(`抓取服务不可用：${(e as Error).message}`);
  }
}

// Forward binary (image) responses untouched.
export async function proxyGetBinary(path: string, search: string, timeoutMs = 20_000): Promise<NextResponse> {
  try {
    const upstream = await fetch(`${pythonBase()}${path}${search}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!upstream.ok) {
      const text = await upstream.text();
      return new NextResponse(text, {
        status: upstream.status,
        headers: { "Content-Type": upstream.headers.get("content-type") || JSON_CT, "Cache-Control": "no-store" },
      });
    }
    const buf = await upstream.arrayBuffer();
    return new NextResponse(buf, {
      status: 200,
      headers: {
        "Content-Type": upstream.headers.get("content-type") || "application/octet-stream",
        "Cache-Control": upstream.headers.get("cache-control") || "public, max-age=86400",
      },
    });
  } catch (e) {
    return errorResponse(`图片代理失败：${(e as Error).message}`);
  }
}

// Forward a JSON POST to the Python service and mirror its response.
export async function proxyPostJson(path: string, body: unknown, timeoutMs = 70_000): Promise<NextResponse> {
  try {
    const upstream = await fetch(`${pythonBase()}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") || JSON_CT, "Cache-Control": "no-store" },
    });
  } catch (e) {
    return errorResponse(`后端服务不可用：${(e as Error).message}`);
  }
}
