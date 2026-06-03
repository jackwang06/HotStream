import { query } from "./db";

export interface RawUserSettings {
  deepseek_api_key: string;
  qwen_api_key: string;
  global_prompt: string;
  text_api_url: string;
  text_api_model: string;
  video_api_url: string;
  video_api_model: string;
  default_prompt: string;
}

const EMPTY_SETTINGS: RawUserSettings = {
  deepseek_api_key: "",
  qwen_api_key: "",
  global_prompt: "",
  text_api_url: "",
  text_api_model: "",
  video_api_url: "",
  video_api_model: "",
  default_prompt: "",
};

export async function getUserSettings(userId: number): Promise<RawUserSettings> {
  const { rows } = await query<RawUserSettings>(
    `SELECT deepseek_api_key, qwen_api_key, global_prompt,
            text_api_url, text_api_model, video_api_url, video_api_model,
            default_prompt
       FROM user_settings WHERE user_id = $1`,
    [userId],
  );
  return rows[0] ?? { ...EMPTY_SETTINGS };
}

// Pass `null` for any field to leave it unchanged. An empty string for
// global_prompt / *_api_url / *_api_model explicitly clears it (= use default);
// empty/blank API keys are treated as "no change" (keys can't be blanked via
// this path — by design).
export async function saveUserSettings(
  userId: number,
  fields: {
    deepseekKey?: string | null;
    qwenKey?: string | null;
    globalPrompt?: string | null;
    textApiUrl?: string | null;
    textApiModel?: string | null;
    videoApiUrl?: string | null;
    videoApiModel?: string | null;
    defaultPrompt?: string | null;
  },
): Promise<void> {
  const deepseek = fields.deepseekKey ?? null;
  const qwen = fields.qwenKey ?? null;
  const prompt = fields.globalPrompt ?? null;
  const textUrl = fields.textApiUrl ?? null;
  const textModel = fields.textApiModel ?? null;
  const videoUrl = fields.videoApiUrl ?? null;
  const videoModel = fields.videoApiModel ?? null;
  const defaultPrompt = fields.defaultPrompt ?? null;
  await query(
    `INSERT INTO user_settings (
       user_id, deepseek_api_key, qwen_api_key, global_prompt,
       text_api_url, text_api_model, video_api_url, video_api_model,
       default_prompt)
     VALUES ($1, COALESCE($2, ''), COALESCE($3, ''), COALESCE($4, ''),
             COALESCE($5, ''), COALESCE($6, ''), COALESCE($7, ''), COALESCE($8, ''),
             COALESCE($9, ''))
     ON CONFLICT (user_id) DO UPDATE SET
       deepseek_api_key = COALESCE($2, user_settings.deepseek_api_key),
       qwen_api_key     = COALESCE($3, user_settings.qwen_api_key),
       global_prompt    = COALESCE($4, user_settings.global_prompt),
       text_api_url     = COALESCE($5, user_settings.text_api_url),
       text_api_model   = COALESCE($6, user_settings.text_api_model),
       video_api_url    = COALESCE($7, user_settings.video_api_url),
       video_api_model  = COALESCE($8, user_settings.video_api_model),
       default_prompt   = COALESCE($9, user_settings.default_prompt),
       updated_at       = now()`,
    [userId, deepseek, qwen, prompt, textUrl, textModel, videoUrl, videoModel, defaultPrompt],
  );
}

// Never expose the raw key to the browser — only whether it's set + a masked tail.
export function maskKey(key: string): { has: boolean; mask: string } {
  if (!key) return { has: false, mask: "" };
  const tail = key.length > 4 ? key.slice(-4) : "";
  return { has: true, mask: `••••${tail}` };
}
