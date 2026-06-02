import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/session";
import LoginForm from "./login-form";

export const dynamic = "force-dynamic";

// Only allow internal, single-leading-slash paths to avoid open-redirect abuse.
function safeNext(next: string | undefined): string {
  if (next && next.startsWith("/") && !next.startsWith("//")) return next;
  return "/app";
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const user = await getCurrentUser();
  const { next } = await searchParams;
  const dest = safeNext(next);
  if (user) redirect(dest);
  return <LoginForm next={dest} />;
}
