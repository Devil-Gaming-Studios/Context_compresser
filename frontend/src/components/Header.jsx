import { NavLink } from 'react-router-dom'
import { useTheme } from '../context/ThemeContext.jsx'

export default function Header() {
  const { theme, toggle } = useTheme()

  return (
    <header className="site-header glass">
      <div className="header-left">
        <NavLink to="/" className="header-brand">
          <span className="brand-logo">◈</span>
          <span className="brand-name">Context Compress</span>
        </NavLink>

        <div className="header-actions">
          <a
            href="/context-compressor-extension.zip"
            download
            className="ext-download"
            title="Download browser extension"
          >
            <span className="ext-icon">⬇</span>
            <span className="ext-label">Extension</span>
            <div className="ext-tooltip glass-strong">
              <p className="ext-tooltip-title">Install the extension</p>
              <ol className="ext-tooltip-steps">
                <li>Unzip the downloaded file</li>
                <li>Open <code>chrome://extensions</code></li>
                <li>Enable <strong>Developer mode</strong></li>
                <li>Click <strong>Load unpacked</strong></li>
                <li>Select the unzipped folder</li>
              </ol>
            </div>
          </a>
        </div>

        <nav className="header-nav">
          <NavLink to="/" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} end>Home</NavLink>
          <NavLink to="/app" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>Compress</NavLink>
          <NavLink to="/docs" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>Docs</NavLink>
        </nav>
      </div>
      <div className="header-right">
        <button className="theme-toggle" onClick={toggle} title="Toggle theme">
          {theme === 'light' ? '◐' : '◑'}
        </button>
      </div>
    </header>
  )
}
