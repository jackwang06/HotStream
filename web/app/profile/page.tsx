import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/session";
import ProfileClient from "./profile-client";

export const dynamic = "force-dynamic";

export default async function ProfilePage() {
  const me = await getCurrentUser();
  if (!me) redirect("/login?next=/profile");

  return <ProfileClient meName={me.displayName || me.username} />;
}
