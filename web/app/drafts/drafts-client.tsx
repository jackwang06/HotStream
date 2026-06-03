"use client";

import { useCallback, useEffect, useState } from "react";
import styles from "./drafts.module.css";
import ThemeToggle from "@/app/theme-toggle";

const IMPORT_KEY = "hotstream.editorDraft";

interface ClientDraft {
  id: number;
  title: string;
  content_blocks: unknown[];
  images: unknown[];
  created_at: string;
  updated_at: string;
}

// 估算字数：content_blocks 既可能是结构化对象数组，也可能是单字符串数组（旧格式）。
function countWords(blocks: unknown[]): number {
  if (!Array.isArray(blocks)) return 0;
  let chars = 0;
  for (const b of blocks) {
    if (typeof b === "string") {
      chars += b.length;
    } else if (b && typeof b === "object") {
      const rec = b as Record<string, unknown>;
      const text = rec.text ?? rec.content ?? rec.value;
      if (typeof text === "string") chars += text.length;
    }
  }
  return chars;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function DraftsClient({ meName }: { meName: string }) {
  const [drafts, setDrafts] = useState<ClientDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean }>({ text: "", ok: true });

  const notify = useCallback((text: string, ok: boolean) => setMsg({ text, ok }), []);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch("/api/drafts", { cache: "no-store" });
      const d = await r.json();
      if (d.success) {
        setDrafts(d.drafts as ClientDraft[]);
      } else {
        notify(d.error || "加载草稿失败", false);
      }
    } catch {
      notify("网络错误，无法加载草稿", false);
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // 打开：拉取完整草稿，按交接约定写入 localStorage 再跳转编辑器。
  async function openDraft(d: ClientDraft) {
    setBusy(true);
    notify("", true);
    try {
      const r = await fetch(`/api/drafts/${d.id}`, { cache: "no-store" });
      const data = await r.json();
      if (!data.success) {
        notify(data.error || "打开草稿失败", false);
        return;
      }
      const draft = data.draft as ClientDraft;
      const cb: unknown[] = Array.isArray(draft.content_blocks) ? draft.content_blocks : [];
      const structured = cb.length > 0 && typeof cb[0] === "object";
      const payload: Record<string, unknown> = {
        id: draft.id,
        title: draft.title || "",
        images: Array.isArray(draft.images) ? draft.images : [],
        updated_at: draft.updated_at,
      };
      if (structured) {
        payload.blocks = cb;
      } else {
        payload.content = (cb as string[]).join("\n\n");
      }
      localStorage.setItem(IMPORT_KEY, JSON.stringify(payload));
      window.location.href = "/editor";
    } catch {
      notify("网络错误，无法打开草稿", false);
    } finally {
      setBusy(false);
    }
  }

  async function renameDraft(d: ClientDraft) {
    const name = window.prompt("请输入新的草稿名称：", d.title || "");
    if (name === null) return;
    const title = name.trim();
    if (!title) {
      notify("草稿名称不能为空", false);
      return;
    }
    setBusy(true);
    notify("", true);
    try {
      const r = await fetch(`/api/drafts/${d.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          content_blocks: d.content_blocks ?? [],
          images: d.images ?? [],
        }),
      });
      const data = await r.json();
      if (data.success) {
        notify(`已重命名为「${title}」`, true);
        await refresh();
      } else {
        notify(data.error || "重命名失败", false);
      }
    } catch {
      notify("网络错误，无法重命名", false);
    } finally {
      setBusy(false);
    }
  }

  async function deleteDraft(d: ClientDraft) {
    if (!window.confirm(`确定删除草稿「${d.title || "未命名草稿"}」？此操作不可撤销。`)) return;
    setBusy(true);
    notify("", true);
    try {
      const r = await fetch(`/api/drafts/${d.id}`, { method: "DELETE" });
      const data = await r.json();
      if (data.success) {
        notify("已删除草稿", true);
        await refresh();
      } else {
        notify(data.error || "删除失败", false);
      }
    } catch {
      notify("网络错误，无法删除", false);
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

  return (
    <div className={styles.page}>
      <div className={styles.top}>
        <h1 className={styles.title}>
          <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <path d="M14 2v6h6" />
            <path d="M16 13H8" />
            <path d="M16 17H8" />
            <path d="M10 9H8" />
          </svg>
          草稿管理
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
          <a className={styles.link} href="/presets">
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 2H2v10l9.29 9.29c.94.94 2.48.94 3.42 0l6.58-6.58c.94-.94.94-2.48 0-3.42L12 2Z" />
              <path d="M7 7h.01" />
            </svg>
            预设
          </a>
          <a className={styles.link} href="/profile">
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
            用户信息
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

      <div className={styles.card}>
        <h2 className={styles.cardTitle}>我的草稿（{drafts.length}）</h2>

        {loading ? (
          <div className={styles.empty}>正在加载草稿…</div>
        ) : drafts.length === 0 ? (
          <div className={styles.empty}>
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <path d="M14 2v6h6" />
            </svg>
            <p className={styles.emptyText}>还没有任何草稿。</p>
            <a className={styles.btn} href="/">
              去首页生成文案
            </a>
          </div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>草稿名称</th>
                <th>字数</th>
                <th>更新时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {drafts.map((d) => (
                <tr key={d.id}>
                  <td className={styles.nameCell}>{d.title || <span className={styles.untitled}>未命名草稿</span>}</td>
                  <td>{countWords(d.content_blocks)}</td>
                  <td className={styles.timeCell}>{formatTime(d.updated_at)}</td>
                  <td>
                    <div className={styles.actions}>
                      <button className={styles.btnGhost} disabled={busy} onClick={() => openDraft(d)}>
                        <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="M15 3h6v6" />
                          <path d="M10 14 21 3" />
                          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                        </svg>
                        打开
                      </button>
                      <button className={styles.btnGhost} disabled={busy} onClick={() => renameDraft(d)}>
                        <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="M12 20h9" />
                          <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z" />
                        </svg>
                        重命名
                      </button>
                      <button className={`${styles.btnGhost} ${styles.btnDanger}`} disabled={busy} onClick={() => deleteDraft(d)}>
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
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className={`${styles.msg} ${msg.ok ? styles.msgOk : styles.msgError}`}>{msg.text}</div>
      </div>
    </div>
  );
}
