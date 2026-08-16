'use client';

import styles from './TopBar.module.css';

interface TopBarProps {
  onMenuClick: () => void;
  title: string;
}

export default function TopBar({ onMenuClick, title }: TopBarProps) {
  return (
    <header className={styles.topbar}>
      <div className={styles.left}>
        <button className={styles.menuBtn} onClick={onMenuClick}>
          <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" width="24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>
        </button>
        <h1 className={styles.title}>{title}</h1>
      </div>

      <div className={styles.search}>
        <span className={styles.searchIcon}>
          <svg fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
        </span>
        <input type="text" placeholder="Search for models..." />
      </div>

      <div className={styles.right}>
        <div className={styles.user}>
          <div className={styles.avatar}>A</div>
          <div className={styles.userInfo}>
            <span className={styles.userName}>Admin User</span>
            <span className={styles.userRole}>Super Admin</span>
          </div>
        </div>
      </div>
    </header>
  );
}
