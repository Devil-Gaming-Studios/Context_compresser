import { createContext, useContext, useState, useCallback } from 'react'

const AppContext = createContext(null)

export function AppProvider({ children }) {
  const [model, setModel] = useState('default')

  const [textInput, setTextInput] = useState('')
  const [textFile, setTextFile] = useState(null)
  const [textContentType, setTextContentType] = useState('auto')
  const [textPreset, setTextPreset] = useState('balanced')
  const [textTarget, setTextTarget] = useState(0.70)
  const [textResult, setTextResult] = useState(null)
  const [textLoading, setTextLoading] = useState(false)
  const [textError, setTextError] = useState(null)

  const [diffText, setDiffText] = useState('')
  const [diffFileContents, setDiffFileContents] = useState({})
  const [diffPrUrl, setDiffPrUrl] = useState('')
  const [diffMode, setDiffMode] = useState('manual')
  const [diffResult, setDiffResult] = useState(null)
  const [diffLoading, setDiffLoading] = useState(false)
  const [diffError, setDiffError] = useState(null)

  const [sessionExport, setSessionExport] = useState('')
  const [sessionFileName, setSessionFileName] = useState('')
  const [sessionProtectRecent, setSessionProtectRecent] = useState(4)
  const [sessionTarget, setSessionTarget] = useState(0.70)
  const [sessionDedupThreshold, setSessionDedupThreshold] = useState(0.9)
  const [sessionResult, setSessionResult] = useState(null)
  const [sessionLoading, setSessionLoading] = useState(false)
  const [sessionError, setSessionError] = useState(null)

  const [presets, setPresets] = useState(null)

  const resetText = useCallback(() => {
    setTextInput('')
    setTextFile(null)
    setTextContentType('auto')
    setTextPreset('balanced')
    setTextTarget(0.70)
    setTextResult(null)
    setTextError(null)
  }, [])

  const resetDiff = useCallback(() => {
    setDiffText('')
    setDiffFileContents({})
    setDiffPrUrl('')
    setDiffMode('manual')
    setDiffResult(null)
    setDiffError(null)
  }, [])

  const resetSession = useCallback(() => {
    setSessionExport('')
    setSessionFileName('')
    setSessionProtectRecent(4)
    setSessionTarget(0.70)
    setSessionDedupThreshold(0.9)
    setSessionResult(null)
    setSessionError(null)
  }, [])

  return (
    <AppContext.Provider
      value={{
        model, setModel,
        textInput, setTextInput,
        textFile, setTextFile,
        textContentType, setTextContentType,
        textPreset, setTextPreset,
        textTarget, setTextTarget,
        textResult, setTextResult,
        textLoading, setTextLoading,
        textError, setTextError,
        diffText, setDiffText,
        diffFileContents, setDiffFileContents,
        diffPrUrl, setDiffPrUrl,
        diffMode, setDiffMode,
        diffResult, setDiffResult,
        diffLoading, setDiffLoading,
        diffError, setDiffError,
        sessionExport, setSessionExport,
        sessionFileName, setSessionFileName,
        sessionProtectRecent, setSessionProtectRecent,
        sessionTarget, setSessionTarget,
        sessionDedupThreshold, setSessionDedupThreshold,
        sessionResult, setSessionResult,
        sessionLoading, setSessionLoading,
        sessionError, setSessionError,
        presets, setPresets,
        resetText, resetDiff, resetSession,
      }}
    >
      {children}
    </AppContext.Provider>
  )
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be inside AppProvider')
  return ctx
}
