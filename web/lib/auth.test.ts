import { describe, it, expect } from "vitest";
import { hashPassword, verifyPassword, generateSessionToken, hashToken } from "./auth";
import { maskKey } from "./user-settings";

describe("password hashing (scrypt)", () => {
  it("produces a parameterized scrypt hash", async () => {
    const h = await hashPassword("correct horse battery staple");
    expect(h).toMatch(/^scrypt\$N=\d+,r=\d+,p=\d+\$[^$]+\$[^$]+$/);
  });

  it("uses a random salt (two hashes of same password differ)", async () => {
    const a = await hashPassword("samePassword123");
    const b = await hashPassword("samePassword123");
    expect(a).not.toEqual(b);
  });

  it("verifies the correct password", async () => {
    const h = await hashPassword("ChangeMe_2026!");
    expect(await verifyPassword("ChangeMe_2026!", h)).toBe(true);
  });

  it("rejects a wrong password", async () => {
    const h = await hashPassword("ChangeMe_2026!");
    expect(await verifyPassword("wrong", h)).toBe(false);
  });

  it("rejects null / malformed stored hashes (and never throws)", async () => {
    expect(await verifyPassword("x", null)).toBe(false);
    expect(await verifyPassword("x", undefined)).toBe(false);
    expect(await verifyPassword("x", "not-a-hash")).toBe(false);
    expect(await verifyPassword("x", "scrypt$bad$bad$bad")).toBe(false);
  });
});

describe("session tokens", () => {
  it("generates 32-byte base64url tokens", () => {
    const t = generateSessionToken();
    expect(t).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(t.length).toBe(43); // base64url of 32 bytes
  });

  it("hashes tokens deterministically to sha256 hex", () => {
    const t = "abc";
    expect(hashToken(t)).toEqual(hashToken(t));
    expect(hashToken(t)).toMatch(/^[0-9a-f]{64}$/);
    expect(hashToken("a")).not.toEqual(hashToken("b"));
  });
});

describe("API key masking", () => {
  it("reports no key for empty", () => {
    expect(maskKey("")).toEqual({ has: false, mask: "" });
  });
  it("masks all but the last 4 chars", () => {
    expect(maskKey("sk-1234567890ABCD")).toEqual({ has: true, mask: "••••ABCD" });
  });
  it("masks short keys without leaking", () => {
    expect(maskKey("abc")).toEqual({ has: true, mask: "••••" });
  });
});
