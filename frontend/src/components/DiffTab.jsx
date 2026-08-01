import { useState, useCallback } from 'react'
import { useApp } from '../context/AppContext.jsx'
import { compressDiff, compressDiffGithub } from '../hooks/useApi.js'
import FileDropZone from './FileDropZone.jsx'
import StatCards from './StatCards.jsx'
import DiffView from './DiffView.jsx'

export default function DiffTab() {
  const {
    model,
    diffText, setDiffText,
    diffFileContents, setDiffFileContents,
    diffPrUrl, setDiffPrUrl,
    diffMode, setDiffMode,
    diffResult, setDiffResult,
    diffLoading, setDiffLoading,
    diffError, setDiffError,
  } = useApp()

  const [parsedFiles, setParsedFiles] = useState([])

  const handleDiffFile = useCallback((file) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const text = e.target.result
      setDiffText(text)
      parseDiffFiles(text)
    }
    reader.readAsText(file)
  }, [setDiffText])

  const parseDiffFiles = (text) => {
    const matches = [...text.matchAll(/^\+\+\+ b\/(.+)$/gm)]
    const files = matches.map((m) => m[1])
    setParsedFiles(files)
    const init = {}
    files.forEach((f) => { init[f] = diffFileContents[f] || '' })
    setDiffFileContents((prev) => ({ ...prev, ...init }))
  }

  const updateFileContent = (path, value) => {
    setDiffFileContents((prev) => ({ ...prev, [path]: value }))
  }

  const runCompress = useCallback(async () => {
    setDiffLoading(true)
    setDiffError(null)
    setDiffResult(null)
    try {
      let data
      if (diffMode === 'github') {
        data = await compressDiffGithub({
          pr: diffPrUrl,
          model,
        })
      } else {
        data = await compressDiff({
          diff_text: diffText,
          file_contents: diffFileContents,
          model,
        })
      }
      setDiffResult(data)
    } catch (err) {
      const msg = err.message === 'Failed to fetch' ? "Can't reach the API" : err.message
      setDiffError(msg)
    } finally {
      setDiffLoading(false)
    }
  }, [model, diffText, diffFileContents, diffPrUrl, diffMode, setDiffLoading, setDiffError, setDiffResult])

  const allFilesProvided = parsedFiles.length === 0 || parsedFiles.every((f) => diffFileContents[f]?.trim())

  return (
    <div className="tab-panel diff-tab">
      <div className="workspace-columns">
        <div className="column input-col">
          <div className="panel-header">Diff Input</div>

          <div className="diff-mode-toggle">
            <button className={`seg-btn ${diffMode === 'manual' ? 'active' : ''}`} onClick={() => setDiffMode('manual')}>
              Manual diff
            </button>
            <button className={`seg-btn ${diffMode === 'github' ? 'active' : ''}`} onClick={() => setDiffMode('github')}>
              GitHub PR
            </button>
          </div>

          {diffMode === 'manual' ? (
            <>
              <textarea
                className="code-input"
                placeholder="Paste unified diff here…"
                value={diffText}
                onChange={(e) => {
                  setDiffText(e.target.value)
                  parseDiffFiles(e.target.value)
                }}
                spellCheck={false}
              />
              <div className="or-divider">or drop a .diff / .patch</div>
              <FileDropZone onFile={handleDiffFile} accept=".diff,.patch" label="Drop diff file here" />

              {parsedFiles.length > 0 && (
                <div className="file-contents-list">
                  <div className="panel-subheader">
                    Provide new file contents for changed files
                  </div>
                  {parsedFiles.map((path) => (
                    <div key={path} className="file-content-card">
                      <label className="file-path">{path}</label>
                      <textarea
                        className="code-input mini"
                        placeholder={`Paste new content for ${path}`}
                        value={diffFileContents[path] || ''}
                        onChange={(e) => updateFileContent(path, e.target.value)}
                        spellCheck={false}
                      />
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="github-input">
              <input
                className="text-input"
                type="text"
                placeholder="https://github.com/owner/repo/pull/123"
                value={diffPrUrl}
                onChange={(e) => setDiffPrUrl(e.target.value)}
              />
              <p className="hint">Backend fetches the diff and file contents for public repos.</p>
            </div>
          )}

          <button
            className="btn-primary btn-full"
            onClick={runCompress}
            disabled={diffLoading || (diffMode === 'manual' ? (!diffText.trim() || !allFilesProvided) : !diffPrUrl.trim())}
          >
            {diffLoading ? 'Compressing…' : 'Compress →'}
          </button>

          {diffError && <div className="alert error">{diffError}</div>}
        </div>

        <div className="column output-col">
          <div className="panel-header">Output</div>
          {diffResult ? (
            <div className="results-stack">
              <StatCards
                stats={[
                  { label: 'Original tokens', value: diffResult.original_tokens?.toLocaleString() ?? '—' },
                  { label: 'Compressed tokens', value: diffResult.compressed_tokens?.toLocaleString() ?? '—' },
                  { label: 'Reduction', value: `${Math.round((diffResult.compression_ratio ?? 0) * 100)}%` },
                  { label: 'Files', value: diffResult.files?.length ?? 0 },
                ]}
              />

              {diffResult.files_skipped && diffResult.files_skipped.length > 0 && (
                <div className="alert warn">
                  Skipped files (no content provided): {diffResult.files_skipped.join(', ')}
                </div>
              )}

              <div className="file-results">
                {diffResult.files?.map((file) => (
                  <details key={file.path} className="file-result-card">
                    <summary>
                      <span className="file-path">{file.path}</span>
                      <span className="file-meta">
                        {file.original_tokens} → {file.compressed_tokens} tokens
                      </span>
                    </summary>
                    <div className="file-stats">
                      <span>changed: {file.changed_blocks_kept}</span>
                      <span>context: {file.context_blocks_kept}</span>
                      <span>deps restored: {file.dependency_blocks_restored}</span>
                      <span>total: {file.blocks_total}</span>
                    </div>
                    <DiffView lines={file.diff_lines} />
                  </details>
                ))}
              </div>

              {diffResult.notes && diffResult.notes.length > 0 && (
                <details className="notes-details">
                  <summary>Pipeline notes ({diffResult.notes.length})</summary>
                  <ul>
                    {diffResult.notes.map((n, i) => (
                      <li key={i}>{n}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          ) : (
            <div className="empty-state">Results will appear here after compression.</div>
          )}
        </div>
      </div>
    </div>
  )
}
