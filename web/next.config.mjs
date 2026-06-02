/** @type {import('next').NextConfig} */
const nextConfig = {
  // Lean container image: copies only the minimal server + traced deps.
  output: "standalone",
  // We serve the legacy HTML and remote/proxied images ourselves; skip the
  // next/image optimizer (which would otherwise want `sharp`, painful on Alpine).
  images: { unoptimized: true },
  // The repo root is the parent dir (Python lives there); pin tracing to web/.
  outputFileTracingRoot: import.meta.dirname,
};

export default nextConfig;
