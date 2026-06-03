"use client";

import { useState } from "react";
import styles from "./admin.module.css";
import ThemeToggle from "@/app/theme-toggle";

export interface ClientUser {
  id: number;
  username: string;
  display_name: string;
  role: "admin" | "user";
  is_active: boolean;
  created_at: string;
}

export default function UsersClient({
  meId,
  meName,
  initialUsers,
}: {
  meId: number;
  meName: string;
  initialUsers: ClientUser[];
}) {
  const [users, setUsers] = useState<ClientUser[]>(initialUsers);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<"admin" | "user">("user");
  const [msg, setMsg] = useState<{ text: string; ok: boolean }>({ text: "", ok: true });
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const r = await fetch("/api/users", { cache: "no-store" });
    const d = await r.json();
    if (d.success) setUsers(d.users);
  }

  function notify(text: string, ok: boolean) {
    setMsg({ text, ok });
  }

  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    notify("", true);
    try {
      const r = await fetch("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, displayName, role }),
      });
      const d = await r.json();
      if (d.success) {
        notify(`已创建用户 ${username}`, true);
        setUsername("");
        setPassword("");
        setDisplayName("");
        setRole("user");
        await refresh();
      } else {
        notify(d.error || "创建失败", false);
      }
    } catch {
      notify("网络错误", false);
    } finally {
      setBusy(false);
    }
  }

  async function patch(id: number, body: Record<string, unknown>, okText: string) {
    setBusy(true);
    notify("", true);
    try {
      const r = await fetch(`/api/users/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (d.success) {
        notify(okText, true);
        await refresh();
      } else {
        notify(d.error || "操作失败", false);
      }
    } catch {
      notify("网络错误", false);
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword(u: ClientUser) {
    const pw = window.prompt(`为「${u.username}」设置新密码（至少 6 位）：`);
    if (!pw) return;
    await patch(u.id, { password: pw }, `已重置 ${u.username} 的密码`);
  }

  async function removeUser(u: ClientUser) {
    if (!window.confirm(`确定删除用户「${u.username}」？若其拥有草稿/历史将无法删除，请改为停用。`)) return;
    setBusy(true);
    notify("", true);
    try {
      const r = await fetch(`/api/users/${u.id}`, { method: "DELETE" });
      const d = await r.json();
      if (d.success) {
        notify(`已删除 ${u.username}`, true);
        await refresh();
      } else {
        notify(d.error || "删除失败", false);
      }
    } catch {
      notify("网络错误", false);
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
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </svg>
          用户管理
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
        <h2 className={styles.cardTitle}>创建新用户（邀请制，仅管理员可创建）</h2>
        <form className={styles.formRow} onSubmit={createUser}>
          <input
            className={styles.input}
            placeholder="用户名"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="off"
            required
          />
          <input
            className={styles.input}
            placeholder="初始密码（≥6 位）"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            required
          />
          <input
            className={styles.input}
            placeholder="显示名（可选）"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            autoComplete="off"
          />
          <select className={styles.select} value={role} onChange={(e) => setRole(e.target.value as "admin" | "user")}>
            <option value="user">普通用户</option>
            <option value="admin">管理员</option>
          </select>
          <button className={styles.btn} type="submit" disabled={busy}>
            创建
          </button>
        </form>
        <div className={`${styles.msg} ${msg.ok ? styles.msgOk : styles.msgError}`}>{msg.text}</div>
      </div>

      <div className={styles.card}>
        <h2 className={styles.cardTitle}>全部用户（{users.length}）</h2>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>ID</th>
              <th>用户名</th>
              <th>显示名</th>
              <th>角色</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const isSelf = u.id === meId;
              return (
                <tr key={u.id}>
                  <td>{u.id}</td>
                  <td>
                    {u.username}
                    {isSelf && <span className={styles.self}> （我）</span>}
                  </td>
                  <td>{u.display_name}</td>
                  <td>
                    <span className={`${styles.badge} ${u.role === "admin" ? styles.badgeAdmin : styles.badgeUser}`}>
                      {u.role === "admin" ? "管理员" : "普通"}
                    </span>
                  </td>
                  <td>
                    <span className={`${styles.badge} ${u.is_active ? styles.badgeActive : styles.badgeInactive}`}>
                      {u.is_active ? "启用" : "停用"}
                    </span>
                  </td>
                  <td>
                    <div className={styles.actions}>
                      <button
                        className={styles.btnGhost}
                        disabled={busy}
                        onClick={() => patch(u.id, { isActive: !u.is_active }, u.is_active ? `已停用 ${u.username}` : `已启用 ${u.username}`)}
                      >
                        {u.is_active ? "停用" : "启用"}
                      </button>
                      <button
                        className={styles.btnGhost}
                        disabled={busy}
                        onClick={() =>
                          patch(u.id, { role: u.role === "admin" ? "user" : "admin" }, `已更新 ${u.username} 的角色`)
                        }
                      >
                        {u.role === "admin" ? "设为普通" : "设为管理员"}
                      </button>
                      <button className={styles.btnGhost} disabled={busy} onClick={() => resetPassword(u)}>
                        重置密码
                      </button>
                      <button
                        className={`${styles.btnGhost} ${styles.btnDanger}`}
                        disabled={busy}
                        onClick={() => removeUser(u)}
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
