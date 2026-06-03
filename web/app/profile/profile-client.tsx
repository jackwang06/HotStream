"use client";

import { useCallback, useEffect, useState } from "react";
import styles from "./profile.module.css";
import ThemeToggle from "@/app/theme-toggle";

// 运行时默认值（与服务端契约一致；空字符串表示沿用这些默认值）。
const TEXT_DEFAULT_URL = "https://api.deepseek.com";
const TEXT_DEFAULT_MODEL = "deepseek-chat";
const VIDEO_DEFAULT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1";
const VIDEO_DEFAULT_MODEL = "qwen-vl-max";

export default function ProfileClient({ meName }: { meName: string }) {
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean }>({ text: "", ok: true });

  // 文案生成 API
  const [textUrl, setTextUrl] = useState("");
  const [textModel, setTextModel] = useState("");
  const [textKey, setTextKey] = useState("");
  const [hasTextKey, setHasTextKey] = useState(false);
  const [textKeyMask, setTextKeyMask] = useState("");

  // 视频分析 API
  const [videoUrl, setVideoUrl] = useState("");
  const [videoModel, setVideoModel] = useState("");
  const [videoKey, setVideoKey] = useState("");
  const [hasVideoKey, setHasVideoKey] = useState(false);
  const [videoKeyMask, setVideoKeyMask] = useState("");

  // 代理灵魂 (global_prompt) 与 默认提示词 (default_prompt)
  const [globalPrompt, setGlobalPrompt] = useState("");
  const [defaultPrompt, setDefaultPrompt] = useState("");

  // 出厂默认值（来自 /api/prompt-defaults，仅代理灵魂需要）
  const [defaultSoul, setDefaultSoul] = useState("");

  const notify = useCallback((text: string, ok: boolean) => setMsg({ text, ok }), []);

  const load = useCallback(async () => {
    try {
      const r = await fetch("/api/settings", { cache: "no-store" });
      const d = await r.json();
      if (d.success) {
        setTextUrl(d.textApiUrl || "");
        setTextModel(d.textApiModel || "");
        setHasTextKey(Boolean(d.hasDeepseekKey));
        setTextKeyMask(d.deepseekKeyMask || "");

        setVideoUrl(d.videoApiUrl || "");
        setVideoModel(d.videoApiModel || "");
        setHasVideoKey(Boolean(d.hasQwenKey));
        setVideoKeyMask(d.qwenKeyMask || "");

        setGlobalPrompt(d.global_prompt || "");
        setDefaultPrompt(d.default_prompt || "");
      } else {
        notify(d.error || "加载配置失败", false);
      }
    } catch {
      notify("网络错误，无法加载配置", false);
    } finally {
      setLoading(false);
    }
  }, [notify]);

  const loadPromptDefaults = useCallback(async () => {
    try {
      const r = await fetch("/api/prompt-defaults", { cache: "no-store" });
      if (!r.ok) return;
      const d = await r.json();
      if (d.success) {
        setDefaultSoul(d.default_soul || "");
      }
    } catch {
      /* non-critical, ignore */
    }
  }, []);

  useEffect(() => {
    void load();
    void loadPromptDefaults();
  }, [load, loadPromptDefaults]);

  async function save() {
    setBusy(true);
    notify("", true);
    try {
      // key 留空则不发送该字段（沿用现有语义，留空=不变）；url/model/global_prompt 原样发送。
      const body: Record<string, unknown> = {
        text_api_url: textUrl,
        text_api_model: textModel,
        video_api_url: videoUrl,
        video_api_model: videoModel,
        global_prompt: globalPrompt,
      };
      if (textKey.trim()) body.deepseek_api_key = textKey;
      if (videoKey.trim()) body.qwen_api_key = videoKey;

      const r = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (d.success) {
        notify("已保存", true);
        setTextKey("");
        setVideoKey("");
        await load();
      } else {
        notify(d.error || "保存失败", false);
      }
    } catch {
      notify("网络错误，无法保存", false);
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {
      /* ignore */
    }
    window.location.href = "/login";
  }

  const textKeyPlaceholder = hasTextKey
    ? `已配置 ••••${textKeyMask || ""}，留空不改`
    : "输入文案生成 API Key";
  const videoKeyPlaceholder = hasVideoKey
    ? `已配置 ••••${videoKeyMask || ""}，留空不改`
    : "输入视频分析 API Key";

  return (
    <div className={styles.page}>
      <div className={styles.top}>
        <h1 className={styles.title}>
          <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
          用户信息
        </h1>
        <div className={styles.topRight}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <svg className="icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
            {meName}
          </span>
          <a className={styles.link} href="/knowledge">
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
            </svg>
            知识库
          </a>
          <a className={styles.link} href="/drafts">
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <path d="M14 2v6h6" />
              <path d="M16 13H8" />
              <path d="M16 17H8" />
              <path d="M10 9H8" />
            </svg>
            草稿
          </a>
          <a className={styles.link} href="/presets">
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 2H2v10l9.29 9.29c.94.94 2.48.94 3.42 0l6.58-6.58c.94-.94.94-2.48 0-3.42L12 2Z" />
              <path d="M7 7h.01" />
            </svg>
            预设
          </a>
          <a className={styles.link} href="/app">
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="m12 19-7-7 7-7" />
              <path d="M19 12H5" />
            </svg>
            返回应用
          </a>
          <ThemeToggle />
          <button className={styles.logout} onClick={logout}>
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="m16 17 5-5-5-5" />
              <path d="M21 12H9" />
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            </svg>
            登出
          </button>
        </div>
      </div>

      {loading ? (
        <div className={styles.card}>
          <div className={styles.loadingText}>正在加载配置…</div>
        </div>
      ) : (
        <>
          <div className={styles.card}>
            <h2 className={styles.cardTitle}>文案生成 API（OpenAI 兼容，默认 DeepSeek）</h2>
            <div className={styles.field}>
              <label className={styles.label}>Base URL</label>
              <input
                className={styles.input}
                placeholder={TEXT_DEFAULT_URL}
                value={textUrl}
                onChange={(e) => setTextUrl(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>模型</label>
              <input
                className={styles.input}
                placeholder={TEXT_DEFAULT_MODEL}
                value={textModel}
                onChange={(e) => setTextModel(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>API Key</label>
              <input
                className={styles.input}
                type="password"
                placeholder={textKeyPlaceholder}
                value={textKey}
                onChange={(e) => setTextKey(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
            </div>
            <p className={styles.hint}>留空 Base URL / 模型即使用默认值。后端为 OpenAI 兼容 /chat/completions。</p>
          </div>

          <div className={styles.card}>
            <h2 className={styles.cardTitle}>视频分析 API（OpenAI 兼容，默认 Qwen）</h2>
            <div className={styles.field}>
              <label className={styles.label}>Base URL</label>
              <input
                className={styles.input}
                placeholder={VIDEO_DEFAULT_URL}
                value={videoUrl}
                onChange={(e) => setVideoUrl(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>模型</label>
              <input
                className={styles.input}
                placeholder={VIDEO_DEFAULT_MODEL}
                value={videoModel}
                onChange={(e) => setVideoModel(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>API Key</label>
              <input
                className={styles.input}
                type="password"
                placeholder={videoKeyPlaceholder}
                value={videoKey}
                onChange={(e) => setVideoKey(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
            </div>
            <p className={styles.hint}>留空 Base URL / 模型即使用默认值。后端为 OpenAI 兼容 /chat/completions。</p>
          </div>

          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>代理灵魂</h2>
              <button
                type="button"
                className={styles.btnGhost}
                onClick={() => setGlobalPrompt(defaultSoul)}
                disabled={!defaultSoul}
              >
                <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                  <path d="M3 3v5h5" />
                </svg>
                恢复默认
              </button>
            </div>
            <textarea
              className={styles.textarea}
              placeholder="AI 人设 / 系统提示（可选），为空则使用系统默认人设"
              value={globalPrompt}
              onChange={(e) => setGlobalPrompt(e.target.value)}
              rows={6}
              spellCheck={false}
            />
            <p className={styles.hint}>定义 AI 的角色与风格，对所有文案生成生效。为空则回落到系统默认人设。</p>
          </div>

          <div className={styles.card}>
            <h2 className={styles.cardTitle}>默认提示词预设</h2>
            <p className={styles.hint}>当前选用预设的内容将作为首页「本次提示词」的起点。</p>
            {defaultPrompt ? (
              <p className={styles.presetPreview}>{defaultPrompt.length > 120 ? defaultPrompt.slice(0, 120) + "…" : defaultPrompt}</p>
            ) : (
              <p className={styles.presetPreviewEmpty}>（尚未选用任何预设）</p>
            )}
            <a className={styles.btn} href="/presets">
              <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 2H2v10l9.29 9.29c.94.94 2.48.94 3.42 0l6.58-6.58c.94-.94.94-2.48 0-3.42L12 2Z" />
                <path d="M7 7h.01" />
              </svg>
              管理预设 →
            </a>
          </div>

          <div className={styles.saveRow}>
            <button className={styles.btn} onClick={save} disabled={busy}>
              <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
                <path d="M17 21v-8H7v8" />
                <path d="M7 3v5h8" />
              </svg>
              {busy ? "保存中…" : "保存"}
            </button>
            <span className={`${styles.msg} ${msg.ok ? styles.msgOk : styles.msgError}`}>{msg.text}</span>
          </div>
        </>
      )}
    </div>
  );
}
