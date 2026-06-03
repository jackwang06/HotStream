import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/session";
import KnowledgeClient from "./knowledge-client";

export const dynamic = "force-dynamic";

export default async function KnowledgePage() {
  const me = await getCurrentUser();
  if (!me) redirect("/login?next=/knowledge");

  return (
    <KnowledgeClient
      meId={me.id}
      meName={me.displayName || me.username}
      isAdmin={me.role === "admin"}
    />
  );
}
