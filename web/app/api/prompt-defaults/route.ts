import { getCurrentUser, unauthorized } from "@/lib/session";
import { proxyGet } from "@/lib/proxy";

export const dynamic = "force-dynamic";

export async function GET() {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  return proxyGet("/api/prompt-defaults", "", 20_000);
}
