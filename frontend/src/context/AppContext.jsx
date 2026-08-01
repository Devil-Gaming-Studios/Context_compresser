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
        presets, setPresets,
        resetText, resetDiff,
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
