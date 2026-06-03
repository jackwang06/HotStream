"use client";

import { useState } from "react";
import styles from "./login.module.css";
import ThemeToggle from "@/app/theme-toggle";

export default function LoginForm({ next }: { next: string }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        window.location.assign(next);
        return;
      }
      setError(data.error || "登录失败");
    } catch {
      setError("网络错误，请重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.wrap}>
      <div style={{ position: "fixed", top: 16, right: 16, zIndex: 5 }}>
        <ThemeToggle />
      </div>
      <form className={styles.card} onSubmit={onSubmit}>
        <div className={styles.brandRow}>
          <svg
            className="icon"
            viewBox="0 0 24 24"
            width="22"
            height="22"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="m8 3 4 8 5-5 5 15H2L8 3z" />
          </svg>
          <h1 className={styles.brand}>HotStream</h1>
        </div>
        <p className={styles.tag}>前山如画，四季成歌 · 请登录</p>

        <label className={styles.label} htmlFor="username">
          用户名
        </label>
        <input
          id="username"
          className={styles.input}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          autoFocus
          required
        />

        <label className={styles.label} htmlFor="password">
          密码
        </label>
        <input
          id="password"
          className={styles.input}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />

        <button className={styles.button} type="submit" disabled={loading}>
          {loading ? "登录中…" : "登录"}
        </button>

        <div className={styles.error}>{error}</div>
      </form>
    </div>
  );
}
