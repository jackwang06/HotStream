import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/session";
import DraftsClient from "./drafts-client";

export const dynamic = "force-dynamic";

export default async function DraftsPage() {
  const me = await getCurrentUser();
  if (!me) redirect("/login?next=/drafts");

  return <DraftsClient meName={me.displayName || me.username} />;
}
