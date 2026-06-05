"use client";

import { useCallback, useEffect, useState } from "react";
import styles from "./presets.module.css";
import ThemeToggle from "@/app/theme-toggle";

type Kind = "default" | "soul";

interface Preset {
  id: number;
  name: string;
  content: string;
  kind: string;
  created_at: string;
  updated_at: string;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function preview(content: string): string {
  const t = content.trim();
  if (!t) return "（空）";
  return t.length > 120 ? `${t.slice(0, 120)}…` : t;
}

export default function PresetsClient({ meName }: { meName: string }) {
  const [activeTab, setActiveTab] = useState<Kind>("default");

  // default kind state
  const [defaultPresets, setDefaultPresets] = useState<Preset[]>([]);
  const [activePresetId, setActivePresetId] = useState<number | null>(null);

  // soul kind state
  const [soulPresets, setSoulPresets] = useState<Preset[]>([]);
  const [activeSoulPresetId, setActiveSoulPresetId] = useState<number | null>(null);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean }>({ text: "", ok: true });

  // 新建预设表单
  const [newName, setNewName] = useState("");
  const [newContent, setNewContent] = useState("");

  // 内联编辑状态
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editContent, setEditContent] = useState("");

  const notify = useCallback((text: string, ok: boolean) => setMsg({ text, ok }), []);

  const refreshKind = useCallback(async (kind: Kind) => {
    try {
      const r = await fetch(`/api/presets?kind=${kind}`, { cache: "no-store" });
      const d = await r.json();
      if (d.success) {
        if (kind === "default") {
          setDefaultPresets(d.presets as Preset[]);
          setActivePresetId(typeof d.activePresetId === "number" ? d.activePresetId : null);
        } else {
          setSoulPresets(d.presets as Preset[]);
          setActiveSoulPresetId(typeof d.activeSoulPresetId === "number" ? d.activeSoulPresetId : null);
        }
      } else {
        notify(d.error || "加载预设失败", false);
      }
    } catch {
      notify("网络错误，无法加载预设", false);
    }
  }, [notify]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([refreshKind("default"), refreshKind("soul")]);
    } finally {
      setLoading(false);
    }
  }, [refreshKind]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const presets = activeTab === "default" ? defaultPresets : soulPresets;
  const currentActiveId = activeTab === "default" ? activePresetId : activeSoulPresetId;

  async function createPreset() {
    const name = newName.trim();
    if (!name) {
      notify("预设名称不能为空", false);
      return;
    }
    setBusy(true);
    notify("", true);
    try {
      const r = await fetch(`/api/presets?kind=${activeTab}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, content: newContent, kind: activeTab }),
      });
      const d = await r.json();
      if (d.success) {
        notify(`已新建预设「${name}」`, true);
        setNewName("");
        setNewContent("");
        await refreshKind(activeTab);
      } else {
        notify(d.error || "新建失败", false);
      }
    } catch {
      notify("网络错误，无法新建", false);
    } finally {
      setBusy(false);
    }
  }

  async function selectPreset(p: Preset) {
    if (p.id === currentActiveId) return;
    setBusy(true);
    notify("", true);
    try {
      const r = await fetch(`/api/presets/${p.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: true }),
      });
      const d = await r.json();
      if (d.success) {
        notify(`已选用「${p.name}」`, true);
        await refreshKind(activeTab);
      } else {
        notify(d.error || "选用失败", false);
      }
    } catch {
      notify("网络错误，无法选用", false);
    } finally {
      setBusy(false);
    }
  }

  function startEdit(p: Preset) {
    setEditingId(p.id);
    setEditName(p.name);
    setEditContent(p.content);
    notify("", true);
  }

  function cancelEdit() {
    setEditingId(null);
    setEditName("");
    setEditContent("");
  }

  async function saveEdit(p: Preset) {
    const name = editName.trim();
    if (!name) {
      notify("预设名称不能为空", false);
      return;
    }
    setBusy(true);
    notify("", true);
    try {
      const r = await fetch(`/api/presets/${p.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, content: editContent }),
      });
      const d = await r.json();
      if (d.success) {
        notify(`已保存「${name}」`, true);
        cancelEdit();
        await refreshKind(activeTab);
      } else {
        notify(d.error || "保存失败", false);
      }
    } catch {
      notify("网络错误，无法保存", false);
    } finally {
      setBusy(false);
    }
  }

  async function deletePreset(p: Preset) {
    if (!window.confirm(`确定删除预设「${p.name}」？此操作不可撤销。`)) return;
    setBusy(true);
    notify("", true);
    try {
      const r = await fetch(`/api/presets/${p.id}`, { method: "DELETE" });
      const d = await r.json();
      if (d.success) {
        notify(`已删除「${p.name}」`, true);
        if (editingId === p.id) cancelEdit();
        await refreshKind(activeTab);
      } else {
        notify(d.error || "删除失败", false);
      }
    } catch {
      notify("网络错误，无法删除", false);
    } finally {
      setBusy(false);
    }
  }

  function switchTab(tab: Kind) {
    setActiveTab(tab);
    cancelEdit();
    setNewName("");
    setNewContent("");
    notify("", true);
  }

  async function logout() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {
      /* ignore */
    }
    window.location.href = "/login";
  }

  const newPlaceholderName =
    activeTab === "soul"
      ? "例如：可爱 / 庄重 / 活泼 / 定制人设"
      : "例如：小红书种草 / 抖音口播 / 公众号长文";
  const newPlaceholderContent =
    activeTab === "soul"
      ? "选用该灵魂后，将作为 AI 的系统人设（代理灵魂）生效。可留空。"
      : "选用该预设后，将作为首页「本次提示词」的起点。可留空。";

  return (
    <div className={styles.page}>
      <div className={styles.top}>
        <h1 className={styles.title}>
          <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M9 11H3v10h6V11z" />
            <path d="M21 3h-6v18h6V3z" />
            <path d="M15 7H9v14h6V7z" />
          </svg>
          预设管理
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
            </svg>
            草稿
          </a>
          <a className={styles.link} href="/profile">
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
            设置
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

      {/* 分段切换 */}
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === "soul" ? styles.tabActive : ""}`}
          onClick={() => switchTab("soul")}
        >
          <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 2a5 5 0 1 0 5 5" />
            <path d="M12 12c-4.418 0-8 1.79-8 4v1h16v-1c0-2.21-3.582-4-8-4z" />
            <path d="M17 2l5 5-5 5" />
          </svg>
          代理灵魂预设
        </button>
        <button
          className={`${styles.tab} ${activeTab === "default" ? styles.tabActive : ""}`}
          onClick={() => switchTab("default")}
        >
          <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M9 11H3v10h6V11z" />
            <path d="M21 3h-6v18h6V3z" />
            <path d="M15 7H9v14h6V7z" />
          </svg>
          默认提示词预设
        </button>
      </div>

      {/* 新建预设 */}
      <div className={styles.card}>
        <h2 className={styles.cardTitle}>
          {activeTab === "soul" ? "新建灵魂预设" : "新建提示词预设"}
        </h2>
        <div className={styles.field}>
          <label className={styles.label}>名称（必填）</label>
          <input
            className={styles.input}
            placeholder={newPlaceholderName}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            maxLength={200}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <div className={styles.field}>
          <label className={styles.label}>
            {activeTab === "soul" ? "灵魂内容（系统人设）" : "提示词内容"}
          </label>
          <textarea
            className={styles.textarea}
            placeholder={newPlaceholderContent}
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            rows={5}
          />
        </div>
        <div className={styles.formActions}>
          <button className={styles.btn} disabled={busy || !newName.trim()} onClick={createPreset}>
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 5v14" />
              <path d="M5 12h14" />
            </svg>
            {activeTab === "soul" ? "新建灵魂预设" : "新建预设"}
          </button>
        </div>
      </div>

      {/* 预设列表 */}
      <div className={styles.card}>
        <h2 className={styles.cardTitle}>
          {activeTab === "soul"
            ? `灵魂预设（${presets.length}）`
            : `提示词预设（${presets.length}）`}
        </h2>

        {loading ? (
          <div className={styles.empty}>
            正在加载预设…
          </div>
        ) : presets.length === 0 ? (
          <div className={styles.empty}>
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 11H3v10h6V11z" />
              <path d="M21 3h-6v18h6V3z" />
              <path d="M15 7H9v14h6V7z" />
            </svg>
            <p className={styles.emptyText}>
              {activeTab === "soul"
                ? "还没有任何灵魂预设，使用上方表单新建一条吧。"
                : "还没有任何预设，使用上方表单新建一条吧。"}
            </p>
          </div>
        ) : (
          <ul className={styles.list}>
            {presets.map((p) => {
              const isActive = p.id === currentActiveId;
              const isEditing = editingId === p.id;
              return (
                <li key={p.id} className={`${styles.item} ${isActive ? styles.itemActive : ""}`}>
                  {isEditing ? (
                    <div className={styles.editBox}>
                      <div className={styles.field}>
                        <label className={styles.label}>名称（必填）</label>
                        <input
                          className={styles.input}
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          maxLength={200}
                          autoComplete="off"
                          spellCheck={false}
                        />
                      </div>
                      <div className={styles.field}>
                        <label className={styles.label}>
                          {activeTab === "soul" ? "灵魂内容（系统人设）" : "提示词内容"}
                        </label>
                        <textarea
                          className={styles.textarea}
                          value={editContent}
                          onChange={(e) => setEditContent(e.target.value)}
                          rows={6}
                        />
                      </div>
                      <div className={styles.actions}>
                        <button className={styles.btn} disabled={busy || !editName.trim()} onClick={() => saveEdit(p)}>
                          <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
                            <path d="M17 21v-8H7v8" />
                            <path d="M7 3v5h8" />
                          </svg>
                          保存
                        </button>
                        <button className={styles.btnGhost} disabled={busy} onClick={cancelEdit}>
                          <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d="M18 6 6 18" />
                            <path d="m6 6 12 12" />
                          </svg>
                          取消
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className={styles.itemHead}>
                        <span className={styles.itemName}>{p.name}</span>
                        {isActive && (
                          <span className={styles.badge}>
                            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <path d="M20 6 9 17l-5-5" />
                            </svg>
                            当前选用
                          </span>
                        )}
                      </div>
                      <p className={styles.itemPreview}>{preview(p.content)}</p>
                      <div className={styles.itemMeta}>更新于 {formatTime(p.updated_at)}</div>
                      <div className={styles.actions}>
                        <button
                          className={styles.btnGhost}
                          disabled={busy || isActive}
                          onClick={() => selectPreset(p)}
                        >
                          <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d="M20 6 9 17l-5-5" />
                          </svg>
                          {isActive ? "已选用" : "选用"}
                        </button>
                        <button className={styles.btnGhost} disabled={busy} onClick={() => startEdit(p)}>
                          <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d="M12 20h9" />
                            <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z" />
                          </svg>
                          编辑
                        </button>
                        <button className={`${styles.btnGhost} ${styles.btnDanger}`} disabled={busy} onClick={() => deletePreset(p)}>
                          <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d="M3 6h18" />
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
                            <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                            <path d="M10 11v6" />
                            <path d="M14 11v6" />
                          </svg>
                          删除
                        </button>
                      </div>
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        <div className={`${styles.msg} ${msg.ok ? styles.msgOk : styles.msgError}`}>{msg.text}</div>
      </div>
    </div>
  );
}
