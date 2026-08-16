'use client';

import { useState } from 'react';
import Sidebar from '@/components/Sidebar';
import TopBar from '@/components/TopBar';
import styles from './dashboard.module.css';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);

  return (
    <div className={styles.layout}>
      <Sidebar 
        isMobileOpen={isMobileOpen} 
        setIsMobileOpen={setIsMobileOpen} 
        isCollapsed={isCollapsed}
        setIsCollapsed={setIsCollapsed}
      />
      
      <div className={`${styles.mainWrapper} ${isCollapsed ? styles.mainWrapperCollapsed : ''}`}>
        <TopBar onMenuClick={() => setIsMobileOpen(true)} title="Dashboard" />
        <main className={styles.content}>
          {children}
        </main>
      </div>

      {isMobileOpen && (
        <div 
          className={styles.overlay} 
          onClick={() => setIsMobileOpen(false)}
        />
      )}
    </div>
  );
}
