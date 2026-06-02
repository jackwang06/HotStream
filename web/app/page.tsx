import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/session";

// Root: bounce to the app home if logged in, else to the login page.
export const dynamic = "force-dynamic";

export default async function Home() {
  const user = await getCurrentUser();
  redirect(user ? "/app" : "/login");
}
