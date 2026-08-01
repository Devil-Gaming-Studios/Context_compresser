import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useTheme } from '../context/ThemeContext.jsx'

export default function Header() {
  const { theme, toggle } = useTheme()
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header className={`site-header glass-strong ${scrolled ? 'scrolled' : ''}`}>
      <div className="header-left">
        <NavLink to="/" className="header-brand">
          <span className="brand-logo">◈</span>
          <span className="brand-name">Context Compress</span>
        </NavLink>

        <div className="header-actions">
          <a href="/context-compressor-extension.zip" download className="ext-download" title="Download browser extension">
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
          <a href="/context-compressor-0.1.0.vsix" download className="ext-download" title="Download VS Code extension">
            <span className="ext-icon">⬇</span>
            <span className="ext-label">VS Code</span>
            <div className="ext-tooltip glass-strong">
              <p className="ext-tooltip-title">Install the VS Code extension</p>
              <ol className="ext-tooltip-steps">
                <li>Open the <strong>Extensions</strong> view in VS Code</li>
                <li>Click the <strong>…</strong> menu at the top</li>
                <li>Select <strong>Install from VSIX…</strong></li>
                <li>Choose the downloaded <code>.vsix</code> file</li>
              </ol>
            </div>
          </a>
        </div>

        <nav className="header-nav">
          <NavLink to="/" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} end>Home</NavLink>
          <NavLink to="/app" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>Compress</NavLink>
          <NavLink to="/docs" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>Docs</NavLink>
          <NavLink to="/benchmarks" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>Benchmarks</NavLink>
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
