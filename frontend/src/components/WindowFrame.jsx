export default function WindowFrame({ title, icon, children }) {
  return (
    <div className="window-frame">
      <div className="window-titlebar">
        <div className="window-title">
          <span className="window-icon">{icon}</span>
          <span>{title}</span>
        </div>
        <div className="window-controls">
          <span className="win-btn minimize">−</span>
          <span className="win-btn maximize">□</span>
          <span className="win-btn close">×</span>
        </div>
      </div>
      <div className="window-content">{children}</div>
    </div>
  )
}
