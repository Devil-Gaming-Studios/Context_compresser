import { useState, useCallback } from 'react'
import Layout from './components/Layout.jsx'
import Home from './pages/Home.jsx'
import Compress from './pages/Compress.jsx'
import History from './pages/History.jsx'
import Settings from './pages/Settings.jsx'

const WINDOWS = {
  home: { label: 'Home', icon: '⌂', component: Home },
  compress: { label: 'Compress', icon: '◉', component: Compress },
  history: { label: 'History', icon: '◷', component: History },
  settings: { label: 'Settings', icon: '◎', component: Settings },
}

export default function App() {
  const [activeWindow, setActiveWindow] = useState('home')
  const [openWindows, setOpenWindows] = useState(['home'])

  const openWindow = useCallback((key) => {
    setActiveWindow(key)
    setOpenWindows((prev) => (prev.includes(key) ? prev : [...prev, key]))
  }, [])

  const closeWindow = useCallback((key) => {
    if (key === 'home') return // keep home pinned
    setOpenWindows((prev) => {
      const next = prev.filter((w) => w !== key)
      if (activeWindow === key && next.length > 0) {
        setActiveWindow(next[next.length - 1])
      }
      return next
    })
  }, [activeWindow])

  const ActiveComponent = WINDOWS[activeWindow]?.component || Home

  return (
    <Layout
      windows={WINDOWS}
      activeWindow={activeWindow}
      openWindows={openWindows}
      onSelect={openWindow}
      onClose={closeWindow}
    >
      <ActiveComponent onNavigate={openWindow} />
    </Layout>
  )
}
