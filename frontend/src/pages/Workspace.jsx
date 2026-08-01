import { useSearchParams } from 'react-router-dom'
import ModelSelector from '../components/ModelSelector.jsx'
import TextTab from '../components/TextTab.jsx'
import DiffTab from '../components/DiffTab.jsx'
import PresetsTab from '../components/PresetsTab.jsx'

const TABS = [
  { key: 'text', label: 'Text / Repo' },
  { key: 'diff', label: 'Diff / PR' },
  { key: 'presets', label: 'Presets & Models' },
]

export default function Workspace() {
  const [params, setParams] = useSearchParams()
  const activeTab = params.get('tab') || 'text'
  const setTab = (key) => setParams({ tab: key })

  return (
    <div className="page workspace-page">
      <div className="workspace-shell">
        <div className="workspace-toolbar glass">
          <div className="tab-bar">
            {TABS.map((t) => (
              <button key={t.key} className={`tab-btn ${activeTab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>
                {t.label}
              </button>
            ))}
          </div>
          <ModelSelector />
        </div>
        <div className="workspace-body">
          {activeTab === 'text' && <TextTab />}
          {activeTab === 'diff' && <DiffTab />}
          {activeTab === 'presets' && <PresetsTab />}
        </div>
      </div>
    </div>
  )
}
