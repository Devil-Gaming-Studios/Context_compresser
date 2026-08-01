import { useEffect, useState } from 'react'
import { useStats } from '../hooks/useApi.js'

export default function Home({ onNavigate }) {
  const { data: stats, loading } = useStats()

  return (
    <div className="page home-page">
      <header className="page-header">
        <h1>Dashboard</h1>
        <p className="subtitle">Overview of your compression workspace</p>
      </header>

      <div className="card-grid">
        <div className="card action-card" onClick={() => onNavigate('compress')}>
          <div className="card-icon">◉</div>
          <h3>New Compression</h3>
          <p>Start a new context compression session</p>
          <span className="card-action">Open →</span>
        </div>

        <div className="card action-card" onClick={() => onNavigate('history')}>
          <div className="card-icon">◷</div>
          <h3>History</h3>
          <p>View past compression jobs and results</p>
          <span className="card-action">Open →</span>
        </div>

        <div className="card action-card" onClick={() => onNavigate('settings')}>
          <div className="card-icon">◎</div>
          <h3>Settings</h3>
          <p>Configure backend endpoints and preferences</p>
          <span className="card-action">Open →</span>
        </div>
      </div>

      <div className="card stats-card">
        <h3>Live Stats</h3>
        {loading ? (
          <div className="skeleton-row" />
        ) : (
          <div className="stats-row">
            <div className="stat">
              <span className="stat-value">{stats?.totalJobs ?? 0}</span>
              <span className="stat-label">Total Jobs</span>
            </div>
            <div className="stat">
              <span className="stat-value">{stats?.compressed ?? 0}</span>
              <span className="stat-label">Compressed</span>
            </div>
            <div className="stat">
              <span className="stat-value">{stats?.savedBytes ?? '0 B'}</span>
              <span className="stat-label">Saved</span>
            </div>
            <div className="stat">
              <span className="stat-value">{stats?.avgRatio ?? '0%'}</span>
              <span className="stat-label">Avg Ratio</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
