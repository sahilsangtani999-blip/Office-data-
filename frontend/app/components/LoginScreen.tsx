"use client";

import React, { useState } from "react";
import { loginOfficeUser } from "../auth";
import { AuthUser } from "../types";
import styles from "./LoginScreen.module.css";

interface LoginScreenProps {
  onLoginSuccess: (user: AuthUser) => void;
}

const DEV_ACCOUNTS = [
  { role: "Admin", username: "admin", pass: "admin123", desc: "Full permissions" },
  { role: "Reviewer", username: "reviewer", pass: "reviewer123", desc: "Validate & approve" },
  { role: "Uploader", username: "uploader", pass: "uploader123", desc: "Upload Excel/PDF" },
  { role: "Viewer", username: "viewer", pass: "viewer123", desc: "Read & search only" },
];

export default function LoginScreen({ onLoginSuccess }: LoginScreenProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setErrorMessage("Please enter both username and password.");
      return;
    }

    setLoading(true);
    setErrorMessage(null);

    try {
      const result = await loginOfficeUser(username.trim(), password);
      onLoginSuccess(result.user);
    } catch (err: any) {
      setErrorMessage(err.message || "Authentication failed. Please verify your credentials.");
    } finally {
      setLoading(false);
    }
  };

  const handleQuickLogin = async (u: string, p: string) => {
    setUsername(u);
    setPassword(p);
    setLoading(true);
    setErrorMessage(null);

    try {
      const result = await loginOfficeUser(u, p);
      onLoginSuccess(result.user);
    } catch (err: any) {
      setErrorMessage(err.message || `Failed to sign in as ${u}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.loginContainer}>
      <div className={styles.loginCard}>
        <div className={styles.brandHeader}>
          <span className={styles.brandDot} aria-hidden="true" />
          <h1 className={styles.brandTitle}>RSSB Office Data Platform</h1>
        </div>
        <p className={styles.cardSubtitle}>Internal Office Authentication</p>

        {errorMessage && (
          <div className={styles.errorBanner} role="alert">
            {errorMessage}
          </div>
        )}

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.fieldGroup}>
            <label htmlFor="username" className={styles.label}>
              Office Username
            </label>
            <input
              id="username"
              type="text"
              className={styles.input}
              placeholder="e.g. admin, reviewer, uploader"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              disabled={loading}
              required
            />
          </div>

          <div className={styles.fieldGroup}>
            <label htmlFor="password" className={styles.label}>
              Password
            </label>
            <input
              id="password"
              type="password"
              className={styles.input}
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              disabled={loading}
              required
            />
          </div>

          <button
            type="submit"
            className={styles.submitBtn}
            disabled={loading}
          >
            {loading ? "Signing in..." : "Sign In to Office Platform"}
          </button>
        </form>

        <div className={styles.divider}>
          <span className={styles.dividerText}>Quick Login for Testing</span>
        </div>

        <div className={styles.devSection}>
          <p className={styles.devHeader}>Select an office test role:</p>
          <div className={styles.devButtons}>
            {DEV_ACCOUNTS.map((acc) => (
              <button
                key={acc.username}
                type="button"
                className={styles.devBtn}
                onClick={() => handleQuickLogin(acc.username, acc.pass)}
                disabled={loading}
                title={`Login as ${acc.role} (${acc.username}/${acc.pass})`}
              >
                <span className={styles.devBtnRole}>{acc.role}</span>
                <span className={styles.devBtnCred}>{acc.username}</span>
              </button>
            ))}
          </div>
        </div>

        <p className={styles.footerNote}>
          Protected internal office platform. All activities are recorded and audited.
        </p>
      </div>
    </div>
  );
}
