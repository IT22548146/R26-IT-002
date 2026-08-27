'use client';

import styles from './dashboard.module.css';

export default function DashboardPage() {
  const stats = [
    { name: 'Total Garments', value: '2,543', change: '+12.5%', color: '#6366f1' },
    { name: 'Active Models', value: '18', change: '+2', color: '#8b5cf6' },
    { name: 'Total Users', value: '1,205', change: '+5.4%', color: '#10b981' },
    { name: 'Revenue', value: '$45,210', change: '+18.2%', color: '#f59e0b' },
  ];

  return (
    <div className="animate-fade-in">
      <div className={styles.statsGrid}>
        {stats.map((stat) => (
          <div key={stat.name} className={styles.statCard}>
            <div className={styles.statInfo}>
              <span className={styles.statName}>{stat.name}</span>
              <span className={styles.statValue}>{stat.value}</span>
            </div>
            <div className={styles.statTrend} style={{ color: stat.change.startsWith('+') ? 'var(--success)' : 'var(--error)' }}>
              {stat.change}
            </div>
            <div className={styles.statProgress} style={{ background: `${stat.color}20` }}>
              <div className={styles.statProgressBar} style={{ width: '70%', background: stat.color }}></div>
            </div>
          </div>
        ))}
      </div>

      <div className={styles.mainGrid}>
        <div className={styles.chartSection}>
          <div className={styles.sectionHeader}>
            <h2>Model Performance</h2>
            <select className={styles.select}>
              <option>Last 7 Days</option>
              <option>Last 30 Days</option>
            </select>
          </div>
          <div className={styles.placeholderChart}>
            {/* Visual placeholder for a chart */}
            <div className={styles.chartBar} style={{ height: '40%' }}></div>
            <div className={styles.chartBar} style={{ height: '70%' }}></div>
            <div className={styles.chartBar} style={{ height: '55%' }}></div>
            <div className={styles.chartBar} style={{ height: '90%' }}></div>
            <div className={styles.chartBar} style={{ height: '65%' }}></div>
            <div className={styles.chartBar} style={{ height: '80%' }}></div>
            <div className={styles.chartBar} style={{ height: '50%' }}></div>
          </div>
        </div>

        <div className={styles.activitySection}>
          <div className={styles.sectionHeader}>
            <h2>Recent Activity</h2>
          </div>
          <div className={styles.activityList}>
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className={styles.activityItem}>
                <div className={styles.activityIcon}>
                  <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" width="16"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                </div>
                <div className={styles.activityContent}>
                  <p>New garment model <strong>"Silk Dress V2"</strong> added.</p>
                  <span>2 hours ago</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
