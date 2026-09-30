"use client";

import React from "react";
import { clearAuthSession, loginOfficeUser } from "../auth";
import { AuthUser } from "../types";
import styles from "./Header.module.css";

interface HeaderProps {
  user: AuthUser | null;
  onLogout: () => void;
  onUserChange?: (user: AuthUser) => void;
}

export default function Header({ user, onLogout, onUserChange }: HeaderProps) {
  const handleRoleSwitch = async (role: "admin" | "reviewer" | "uploader" | "viewer") => {
    try {
      const res = await loginOfficeUser(role, `${role}123`);
      if (onUserChange) onUserChange(res.user);
    } catch {
      // Ignored in dev
    }
  };

  const handleLogout = () => {
    clearAuthSession();
    onLogout();
  };

  return (
    <header className={styles.header}>
      <div className={styles.container}>
        <div className={styles.brand}>
          <span className={styles.dot} aria-hidden="true" />
          <h1 className={styles.title}>RSSB Office Data Platform</h1>
        </div>
        <div className={styles.rightGroup}>
          {user && (
            <>
              <div className={styles.roleSelector}>
                <span className={styles.roleLabel}>Role:</span>
                <select
                  className={styles.roleSelect}
                  value={user.role}
                  onChange={(e) => handleRoleSwitch(e.target.value as any)}
                  aria-label="Active Office Role"
                >
                  <option value="admin">Admin</option>
                  <option value="reviewer">Reviewer</option>
                  <option value="uploader">Uploader</option>
                  <option value="viewer">Viewer</option>
                </select>
              </div>

              <div className={styles.userBadge} title={`Signed in as ${user.username}`}>
                <span>{user.username}</span>
                <span className={styles.roleTag}>({user.role})</span>
              </div>

              <button
                type="button"
                className={styles.logoutBtn}
                onClick={handleLogout}
                aria-label="Sign out of office platform"
              >
                Sign Out
              </button>
            </>
          )}
          {!user && <div className={styles.badge}>Internal Office System</div>}
        </div>
      </div>
    </header>
  );
}
