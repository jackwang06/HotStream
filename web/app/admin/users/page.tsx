import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/session";
import { listUsers } from "@/lib/users";
import UsersClient, { type ClientUser } from "./users-client";

export const dynamic = "force-dynamic";

export default async function AdminUsersPage() {
  const me = await getCurrentUser();
  if (!me) redirect("/login?next=/admin/users");
  if (me.role !== "admin") redirect("/app");

  const users = await listUsers();
  const initial: ClientUser[] = users.map((u) => ({
    id: u.id,
    username: u.username,
    display_name: u.display_name,
    role: u.role,
    is_active: u.is_active,
    created_at: u.created_at instanceof Date ? u.created_at.toISOString() : String(u.created_at),
  }));

  return <UsersClient meId={me.id} meName={me.displayName || me.username} initialUsers={initial} />;
}
