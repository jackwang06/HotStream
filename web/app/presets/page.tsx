import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/session";
import PresetsClient from "./presets-client";

export const dynamic = "force-dynamic";

export default async function PresetsPage() {
  const me = await getCurrentUser();
  if (!me) redirect("/login?next=/presets");

  return <PresetsClient meName={me.displayName || me.username} />;
}
