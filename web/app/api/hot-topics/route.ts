import { getCurrentUser, unauthorized } from "@/lib/session";
import { proxyGet } from "@/lib/proxy";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  const search = new URL(req.url).search;
  return proxyGet("/api/hot-topics", search, 20_000);
}
