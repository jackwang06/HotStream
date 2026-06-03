"use client";

import { useCallback, useEffect, useState } from "react";
import styles from "./knowledge.module.css";
import ThemeToggle from "@/app/theme-toggle";

interface KnowledgeItem {
  id: number;
  title: string;
  content: string;
  tags: string;
  enabled: boolean;
  created_by: number | null;
  uploader: string;
  created_at: string;
  updated_at: string;
  canEdit: boolean;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function splitTags(tags: string): string[] {
  return tags
    .split(/[,，\s]+/)
    .map((t) => t.trim())
    .filter(Boolean);
}

export default function KnowledgeClient({
  meName,
}: {
  meId: number;
  meName: string;
  isAdmin: boolean;
}) {
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean }>({ text: "", ok: true });

  // 新增表单
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");

  // 编辑态：记录正在编辑的条目 id 与草稿
  const [editId, setEditId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const [editTags, setEditTags] = useState("");

  // 展开的条目集合
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const notify = useCallback((text: string, ok: boolean) => setMsg({ text, ok }), []);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch("/api/knowledge", { cache: "no-store" });
      const d = await r.json();
      if (d.success) {
        setItems(d.items as KnowledgeItem[]);
      } else {
        notify(d.error || "加载知识库失败", false);
      }
    } catch {
      notify("网络错误，无法加载知识库", false);
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function toggleExpand(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function createItem(e: React.FormEvent) {
    e.preventDefault();
    const t = title.trim();
    const c = content.trim();
    if (!t) {
      notify("标题不能为空", false);
      return;
    }
    if (!c) {
      notify("内容不能为空", false);
      return;
    }
    setBusy(true);
    notify("", true);
    try {
      const r = await fetch("/api/knowledge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: t, content: c, tags: tags.trim() }),
      });
      const d = await r.json();
      if (d.success) {
        notify("已添加到知识库", true);
        setTitle("");
        setContent("");
        setTags("");
        await refresh();
      } else {
        notify(d.error || "添加失败", false);
      }
    } catch {
      notify("网络错误，无法添加", false);
    } finally {
      setBusy(false);
    }
  }

  function beginEdit(item: KnowledgeItem) {
    setEditId(item.id);
    setEditTitle(item.title);
    setEditContent(item.content);
    setEditTags(item.tags);
  }

  function cancelEdit() {
    setEditId(null);
    setEditTitle("");
    setEditContent("");
    setEditTags("");
  }

  async function saveEdit(item: KnowledgeItem) {
    const t = editTitle.trim();
    const c = editContent.trim();
    if (!t) {
      notify("标题不能为空", false);
      return;
    }
    if (!c) {
      notify("内容不能为空", false);
      return;
    }
    setBusy(true);
    notify("", true);
    try {
      const r = await fetch(`/api/knowledge/${item.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: t, content: c, tags: editTags.trim(), enabled: item.enabled }),
      });
      const d = await r.json();
      if (d.success) {
        notify("已保存修改", true);
        cancelEdit();
        await refresh();
      } else {
        notify(d.error || "保存失败", false);
      }
    } catch {
      notify("网络错误，无法保存", false);
    } finally {
      setBusy(false);
    }
  }

  async function toggleEnabled(item: KnowledgeItem) {
    setBusy(true);
    notify("", true);
    try {
      const r = await fetch(`/api/knowledge/${item.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: item.title,
          content: item.content,
          tags: item.tags,
          enabled: !item.enabled,
        }),
      });
      const d = await r.json();
      if (d.success) {
        notify(item.enabled ? "已停用该条目" : "已启用该条目", true);
        await refresh();
      } else {
        notify(d.error || "操作失败", false);
      }
    } catch {
      notify("网络错误，无法操作", false);
    } finally {
      setBusy(false);
    }
  }

  async function deleteItem(item: KnowledgeItem) {
    if (!window.confirm(`确定删除条目「${item.title || "未命名条目"}」？此操作不可撤销。`)) return;
    setBusy(true);
    notify("", true);
    try {
      const r = await fetch(`/api/knowledge/${item.id}`, { method: "DELETE" });
      const d = await r.json();
      if (d.success) {
        notify("已删除条目", true);
        await refresh();
      } else {
        notify(d.error || "删除失败", false);
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
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
          知识库
        </h1>
        <div className={styles.topRight}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <svg className="icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
            {meName}
          </span>
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

      <p className={styles.intro}>
        这里的已启用条目会在生成文案时自动作为景区背景注入；想有针对性就在本次提示词里点明。
      </p>

      <div className={styles.card}>
        <h2 className={styles.cardTitle}>添加知识库条目（全局共享）</h2>
        <form className={styles.form} onSubmit={createItem}>
          <div className={styles.field}>
            <label className={styles.label}>标题</label>
            <input
              className={styles.input}
              placeholder="例如：下个月15号的篝火晚会"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>内容</label>
            <textarea
              className={styles.textarea}
              placeholder="例如：本月15号晚7点在湖边广场举办篝火晚会，含烤全羊、民族歌舞与烟花，免费入场，建议提前到场占位。"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={5}
              spellCheck={false}
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>标签（可选，逗号或空格分隔）</label>
            <input
              className={styles.input}
              placeholder="例如：活动, 夜游, 限时"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className={styles.formActions}>
            <button className={styles.btn} type="submit" disabled={busy}>
              <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 5v14" />
                <path d="M5 12h14" />
              </svg>
              {busy ? "提交中…" : "添加条目"}
            </button>
            <span className={`${styles.msg} ${msg.ok ? styles.msgOk : styles.msgError}`}>{msg.text}</span>
          </div>
        </form>
      </div>

      <div className={styles.card}>
        <h2 className={styles.cardTitle}>全部条目（{items.length}）</h2>

        {loading ? (
          <div className={styles.empty}>正在加载知识库…</div>
        ) : items.length === 0 ? (
          <div className={styles.empty}>
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
            </svg>
            <p className={styles.emptyText}>还没有任何知识库条目。</p>
            <p className={styles.emptyHint}>
              试着把“下个月15号的篝火晚会”这类活动信息加进来，生成文案时就能自动用上。
            </p>
          </div>
        ) : (
          <ul className={styles.list}>
            {items.map((item) => {
              const isEditing = editId === item.id;
              const isOpen = expanded.has(item.id);
              const tagList = splitTags(item.tags);
              return (
                <li key={item.id} className={styles.item}>
                  {isEditing ? (
                    <div className={styles.editForm}>
                      <div className={styles.field}>
                        <label className={styles.label}>标题</label>
                        <input
                          className={styles.input}
                          value={editTitle}
                          onChange={(e) => setEditTitle(e.target.value)}
                          autoComplete="off"
                        />
                      </div>
                      <div className={styles.field}>
                        <label className={styles.label}>内容</label>
                        <textarea
                          className={styles.textarea}
                          value={editContent}
                          onChange={(e) => setEditContent(e.target.value)}
                          rows={5}
                          spellCheck={false}
                        />
                      </div>
                      <div className={styles.field}>
                        <label className={styles.label}>标签（可选）</label>
                        <input
                          className={styles.input}
                          value={editTags}
                          onChange={(e) => setEditTags(e.target.value)}
                          autoComplete="off"
                        />
                      </div>
                      <div className={styles.actions}>
                        <button className={styles.btnGhost} disabled={busy} onClick={() => saveEdit(item)}>
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
                        <div className={styles.itemHeadMain}>
                          <span className={styles.itemTitle}>
                            {item.title || <span className={styles.untitled}>未命名条目</span>}
                          </span>
                          <span className={`${styles.statusBadge} ${item.enabled ? styles.statusOn : styles.statusOff}`}>
                            {item.enabled ? "已启用" : "已停用"}
                          </span>
                        </div>
                        <button
                          className={styles.expandBtn}
                          onClick={() => toggleExpand(item.id)}
                          aria-expanded={isOpen}
                        >
                          {isOpen ? "收起" : "展开"}
                          <svg
                            className="icon"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            aria-hidden="true"
                            style={{ transform: isOpen ? "rotate(180deg)" : "none" }}
                          >
                            <path d="m6 9 6 6 6-6" />
                          </svg>
                        </button>
                      </div>

                      <p className={isOpen ? styles.itemContentFull : styles.itemContentPreview}>{item.content}</p>

                      {tagList.length > 0 && (
                        <div className={styles.tags}>
                          {tagList.map((t, i) => (
                            <span className={styles.tag} key={i}>
                              {t}
                            </span>
                          ))}
                        </div>
                      )}

                      <div className={styles.itemFoot}>
                        <span className={styles.meta}>
                          <svg className="icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
                            <circle cx="12" cy="7" r="4" />
                          </svg>
                          {item.uploader || "未知"}
                        </span>
                        <span className={styles.meta}>更新于 {formatTime(item.updated_at)}</span>
                      </div>

                      {item.canEdit && (
                        <div className={styles.actions}>
                          <button className={styles.btnGhost} disabled={busy} onClick={() => toggleEnabled(item)}>
                            {item.enabled ? (
                              <>
                                <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                  <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
                                  <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
                                  <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
                                  <path d="m2 2 20 20" />
                                </svg>
                                停用
                              </>
                            ) : (
                              <>
                                <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                  <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
                                  <circle cx="12" cy="12" r="3" />
                                </svg>
                                启用
                              </>
                            )}
                          </button>
                          <button className={styles.btnGhost} disabled={busy} onClick={() => beginEdit(item)}>
                            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <path d="M12 20h9" />
                              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z" />
                            </svg>
                            编辑
                          </button>
                          <button className={`${styles.btnGhost} ${styles.btnDanger}`} disabled={busy} onClick={() => deleteItem(item)}>
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
                      )}
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
