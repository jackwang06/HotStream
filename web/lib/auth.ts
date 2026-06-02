import crypto from "node:crypto";
import { promisify } from "node:util";

export { SESSION_COOKIE, SESSION_TTL_DAYS } from "./constants";

// ── Password hashing (scrypt — Node built-in, zero native deps, Alpine-safe) ──
//
// Stored format keeps the cost parameters with the hash so they can be tuned
// later without breaking existing hashes:
//   scrypt$N=16384,r=8,p=1$<salt_b64>$<hash_b64>

const SCRYPT_N = 16_384; // 2^14 — ~16MB working set, under the 32MB default maxmem
const SCRYPT_R = 8;
const SCRYPT_P = 1;
const KEYLEN = 64;
const MAXMEM = 64 * 1024 * 1024;

const scryptAsync = promisify(crypto.scrypt) as (
  password: crypto.BinaryLike,
  salt: crypto.BinaryLike,
  keylen: number,
  options: crypto.ScryptOptions,
) => Promise<Buffer>;

export async function hashPassword(password: string): Promise<string> {
  const salt = crypto.randomBytes(16);
  const derived = await scryptAsync(password, salt, KEYLEN, {
    N: SCRYPT_N,
    r: SCRYPT_R,
    p: SCRYPT_P,
    maxmem: MAXMEM,
  });
  return `scrypt$N=${SCRYPT_N},r=${SCRYPT_R},p=${SCRYPT_P}$${salt.toString("base64")}$${derived.toString("base64")}`;
}

// A fixed valid hash used to equalize timing when a username does not exist,
// preventing user-enumeration via response timing. Computed EAGERLY at module
// load so the very first "user not found" attempt costs exactly one scrypt
// (matching the hit path) instead of two.
const dummyHashPromise: Promise<string> = hashPassword(crypto.randomBytes(16).toString("hex"));
async function getDummyHash(): Promise<string> {
  return dummyHashPromise;
}

export async function verifyPassword(password: string, stored: string | null | undefined): Promise<boolean> {
  // Always perform a scrypt computation, even for missing/invalid stored hashes,
  // so timing does not reveal whether the account exists.
  const target = stored && stored.startsWith("scrypt$") ? stored : await getDummyHash();
  try {
    const [, paramStr, saltB64, hashB64] = target.split("$");
    const params = Object.fromEntries(paramStr.split(",").map((kv) => kv.split("=") as [string, string]));
    const N = Number(params.N);
    const r = Number(params.r);
    const p = Number(params.p);
    const salt = Buffer.from(saltB64, "base64");
    const expected = Buffer.from(hashB64, "base64");
    const derived = await scryptAsync(password, salt, expected.length, { N, r, p, maxmem: MAXMEM });
    if (derived.length !== expected.length) return false;
    const ok = crypto.timingSafeEqual(derived, expected);
    // If we fell back to the dummy hash, never report success.
    return stored && stored.startsWith("scrypt$") ? ok : false;
  } catch {
    return false;
  }
}

// ── Opaque session tokens ──
// The cookie carries a random token; the DB stores only its SHA-256, so a DB
// leak cannot be used to forge live sessions.

export function generateSessionToken(): string {
  return crypto.randomBytes(32).toString("base64url");
}

export function hashToken(token: string): string {
  return crypto.createHash("sha256").update(token).digest("hex");
}
