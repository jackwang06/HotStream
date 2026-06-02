// Edge-safe constants ONLY (no node:* imports) so they can be used from
// middleware (Edge runtime) as well as Node route handlers.
export const SESSION_COOKIE = "hotstream_session";
export const SESSION_TTL_DAYS = 7;
