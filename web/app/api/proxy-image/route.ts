import { NextResponse } from "next/server";
import { getCurrentUser, unauthorized } from "@/lib/session";
import { proxyGetBinary } from "@/lib/proxy";
import { validateImageUrl } from "@/lib/ssrf";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();

  const url = new URL(req.url);
  const target = url.searchParams.get("url") || "";
  const check = validateImageUrl(target);
  if (!check.ok) {
    return NextResponse.json({ success: false, error: check.error }, { status: 400 });
  }
  return proxyGetBinary("/api/proxy-image", url.search, 15_000);
}
