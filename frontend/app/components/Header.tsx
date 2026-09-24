import React from "react";
import styles from "./Header.module.css";

export default function Header() {
  return (
    <header className={styles.header}>
      <div className={styles.container}>
        <div className={styles.brand}>
          <span className={styles.dot} aria-hidden="true" />
          <h1 className={styles.title}>RSSB Office Data Platform</h1>
        </div>
        <div className={styles.badge}>Internal Office System</div>
      </div>
    </header>
  );
}
