import { NavLink } from 'react-router-dom'
import { useApp } from '../context/AppContext.jsx'
import { useHealth } from '../hooks/useApi.js'

export default function Header() {
  const { apiConnected } = useApp()
  useHealth()

  return (
    <header className="site-header">
      <div className="header-left">
        <NavLink to="/" className="header-brand">
          <span className="brand-mark">ctx//</span>
          <span className="brand-name">compress</span>
        </NavLink>
        <nav className="header-nav">
          <NavLink to="/" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} end>
            Home
          </NavLink>
          <NavLink to="/app" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Compress
          </NavLink>
          <NavLink to="/docs" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Docs
          </NavLink>
        </nav>
      </div>
      <div className="header-right">
        <div className={`health-pill ${apiConnected ? 'ok' : 'down'}`}>
          <span className="health-dot" />
          <span className="health-text">{apiConnected ? 'API connected' : 'API offline'}</span>
        </div>
      </div>
    </header>
  )
}
