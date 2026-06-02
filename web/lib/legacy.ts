import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { NextResponse } from "next/server";
import { getCurrentUser } from "./session";

// Serve a legacy single-file HTML page, gated by a real DB-validated session.
// We deliberately keep these OUT of `public/` so they can never be served
// without passing through this authenticated Node handler.
const cache = new Map<string, string>();

async function readLegacy(fileName: string): Promise<string> {
  const cached = cache.get(fileName);
  if (cached !== undefined) return cached;
  const html = await readFile(join(process.cwd(), "legacy", fileName), "utf8");
  cache.set(fileName, html);
  return html;
}

export async function serveLegacy(fileName: string, req: Request): Promise<NextResponse> {
  const user = await getCurrentUser();
  if (!user) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  const html = await readLegacy(fileName);
  return new NextResponse(html, {
    status: 200,
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
  });
}
