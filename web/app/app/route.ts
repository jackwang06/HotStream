import { serveLegacy } from "@/lib/legacy";

export const dynamic = "force-dynamic";

export function GET(req: Request) {
  return serveLegacy("index.html", req);
}
