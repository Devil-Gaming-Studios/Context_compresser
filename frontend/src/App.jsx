import { Routes, Route } from 'react-router-dom'
import { AppProvider } from './context/AppContext.jsx'
import Header from './components/Header.jsx'
import Home from './pages/Home.jsx'
import Workspace from './pages/Workspace.jsx'
import Docs from './pages/Docs.jsx'

export default function App() {
  return (
    <AppProvider>
      <div className="app-root">
        <Header />
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/app" element={<Workspace />} />
          <Route path="/docs" element={<Docs />} />
        </Routes>
      </div>
    </AppProvider>
  )
}
