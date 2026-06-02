import { describe, it, expect } from "vitest";
import { validateImageUrl } from "./ssrf";

describe("validateImageUrl (SSRF guard)", () => {
  it("allows public http/https image URLs", () => {
    expect(validateImageUrl("https://i0.hdslb.com/bfs/archive/abc.jpg").ok).toBe(true);
    expect(validateImageUrl("http://p3.toutiaoimg.com/x.png").ok).toBe(true);
  });

  it("rejects non-http(s) schemes", () => {
    expect(validateImageUrl("file:///etc/passwd").ok).toBe(false);
    expect(validateImageUrl("gopher://x/").ok).toBe(false);
    expect(validateImageUrl("data:text/plain,hi").ok).toBe(false);
  });

  it("blocks loopback / localhost", () => {
    expect(validateImageUrl("http://127.0.0.1/x").ok).toBe(false);
    expect(validateImageUrl("http://localhost:5173/x").ok).toBe(false);
    expect(validateImageUrl("http://[::1]/x").ok).toBe(false);
  });

  it("blocks cloud metadata + link-local", () => {
    expect(validateImageUrl("http://169.254.169.254/latest/meta-data/").ok).toBe(false);
    expect(validateImageUrl("http://metadata.google.internal/").ok).toBe(false);
  });

  it("blocks private ranges", () => {
    expect(validateImageUrl("http://10.0.0.5/x").ok).toBe(false);
    expect(validateImageUrl("http://172.16.3.4/x").ok).toBe(false);
    expect(validateImageUrl("http://192.168.1.1/x").ok).toBe(false);
  });

  it("rejects empty/garbage", () => {
    expect(validateImageUrl("").ok).toBe(false);
    expect(validateImageUrl("not a url").ok).toBe(false);
  });
});
