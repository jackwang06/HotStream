import { getCurrentUser, unauthorized } from "@/lib/session";
import { proxyGet } from "@/lib/proxy";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  const search = new URL(req.url).search;
  // Douyin links can chain several bounded fetches (shortlink resolve + mobile
  // SSR share page); allow extra headroom over the default so a slow-but-working
  // resolve isn't cut off.
  return proxyGet("/api/custom-source", search, 35_000);
}
