import WindowFrame from './WindowFrame.jsx'

export default function Layout({
  windows,
  activeWindow,
  openWindows,
  onSelect,
  onClose,
  children,
}) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="brand-mark">ctx//</span>
          <span className="brand-name">compress</span>
        </div>
        <nav className="sidebar-nav">
          {Object.entries(windows).map(([key, win]) => {
            const isOpen = openWindows.includes(key)
            const isActive = activeWindow === key
            return (
              <button
                key={key}
                className={`nav-item ${isActive ? 'active' : ''} ${isOpen ? 'open' : ''}`}
                onClick={() => onSelect(key)}
                title={win.label}
              >
                <span className="nav-icon">{win.icon}</span>
                <span className="nav-label">{win.label}</span>
                {isOpen && key !== 'home' && (
                  <span
                    className="nav-close"
                    onClick={(e) => {
                      e.stopPropagation()
                      onClose(key)
                    }}
                  >
                    ×
                  </span>
                )}
              </button>
            )
          })}
        </nav>
        <div className="sidebar-footer">
          <span className="status-dot" />
          <span className="status-text">backend ready</span>
        </div>
      </aside>

      <main className="main-stage">
        <WindowFrame
          title={windows[activeWindow]?.label}
          icon={windows[activeWindow]?.icon}
        >
          {children}
        </WindowFrame>
      </main>
    </div>
  )
}
