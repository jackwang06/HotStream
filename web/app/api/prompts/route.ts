import { NextResponse } from "next/server";
import { getCurrentUser, unauthorized, assertSameOrigin } from "@/lib/session";
import { proxyPostJson } from "@/lib/proxy";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    body = {};
  }
  return proxyPostJson("/api/prompts", body, 20_000);
}
