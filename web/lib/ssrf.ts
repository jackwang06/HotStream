// SSRF guard for the image proxy. Pure (no next/* imports) so it is unit-testable.
//
// Image URLs come from arbitrary public CDNs (B站 covers, etc.), so we can't
// allowlist domains — but we can block obviously-internal targets. This stops
// literal private/loopback/link-local/metadata IPs. (DNS-rebind to a private IP
// is a residual risk; acceptable for an authenticated, invite-only internal tool.)
export function isBlockedHost(host: string): boolean {
  const h = host.toLowerCase().replace(/^\[|\]$/g, ""); // strip IPv6 brackets
  if (h === "localhost" || h.endsWith(".localhost") || h.endsWith(".local") || h.endsWith(".internal")) return true;
  if (h === "metadata.google.internal") return true;

  // IPv4 literal?
  const m = h.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (m) {
    const a = Number(m[1]);
    const b = Number(m[2]);
    if (a === 10 || a === 127 || a === 0) return true; // private / loopback / "this host"
    if (a === 169 && b === 254) return true; // link-local (incl. 169.254.169.254 metadata)
    if (a === 172 && b >= 16 && b <= 31) return true; // private
    if (a === 192 && b === 168) return true; // private
    if (a === 100 && b >= 64 && b <= 127) return true; // CGNAT
    return false;
  }
  // IPv6 literal loopback / unspecified / unique-local / link-local
  if (h === "::1" || h === "::") return true;
  if (h.startsWith("fc") || h.startsWith("fd") || h.startsWith("fe80")) return true;
  if (h.startsWith("::ffff:")) return true; // IPv4-mapped — be conservative
  return false;
}

export function validateImageUrl(rawUrl: string): { ok: true } | { ok: false; error: string } {
  if (!rawUrl) return { ok: false, error: "缺少图片地址" };
  let u: URL;
  try {
    u = new URL(rawUrl);
  } catch {
    return { ok: false, error: "图片地址格式不正确" };
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") {
    return { ok: false, error: "图片地址必须是 http/https" };
  }
  if (isBlockedHost(u.hostname)) {
    return { ok: false, error: "拒绝访问内网/本地地址" };
  }
  return { ok: true };
}
