import { pythonBase } from "./proxy";

/**
 * Fetch the factory-default prompt template from the Python service.
 * Returns the `default_prompt` field from GET /api/prompt-defaults, or ""
 * on any error / missing field (best-effort, never throws).
 */
export async function getFactoryDefaultPrompt(): Promise<string> {
  try {
    const resp = await fetch(`${pythonBase()}/api/prompt-defaults`, {
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    if (!resp.ok) return "";
    const data = (await resp.json()) as Record<string, unknown>;
    const val = data?.default_prompt;
    return typeof val === "string" ? val : "";
  } catch {
    return "";
  }
}
