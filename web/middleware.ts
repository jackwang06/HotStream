import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "./lib/constants";

// IMPORTANT: this middleware runs on the Edge runtime. Keep it dependency-free
// (no node:* / pg / crypto). It is only a fast UX gate — it checks for the
// PRESENCE of a session cookie, not its validity. The real security boundary is
// each Node route handler / page, which validates the session against the DB.

const PUBLIC_PAGES = new Set(["/login"]);

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Auth endpoints manage their own session state; let them through.
  if (pathname.startsWith("/api/auth/")) return NextResponse.next();

  // Public static files served from /public (e.g. /login-bg.jpg) — needed by
  // the unauthenticated login page. The matcher already excludes /_next/*;
  // this covers root-level asset files. Auth is still enforced on pages/routes.
  if (/\.(?:jpe?g|png|gif|svg|webp|avif|ico|bmp|woff2?|ttf|otf|eot|css|js|map|txt|webmanifest)$/i.test(pathname)) {
    return NextResponse.next();
  }

  // Public pages.
  if (PUBLIC_PAGES.has(pathname)) return NextResponse.next();

  const hasCookie = Boolean(req.cookies.get(SESSION_COOKIE)?.value);
  if (hasCookie) return NextResponse.next();

  // No session cookie: API calls get 401 JSON (never redirect a fetch to the
  // login HTML — the legacy JS would choke parsing "<" as JSON). Page requests
  // get redirected to /login with a ?next= return path.
  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ success: false, error: "未登录" }, { status: 401 });
  }
  const loginUrl = new URL("/login", req.url);
  loginUrl.searchParams.set("next", pathname + req.nextUrl.search);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  // Run on everything except Next internals and static asset files.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
