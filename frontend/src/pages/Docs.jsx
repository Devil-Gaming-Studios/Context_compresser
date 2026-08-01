export default function Docs() {
  return (
    <div className="page docs-page">
      <h1>How it works</h1>

      <section className="doc-section">
        <h2>Pipeline steps</h2>
        <ol className="pipeline-list">
          <li><strong>Structural strip</strong> — removes redundant imports, closing braces, decorative comments.</li>
          <li><strong>Chunk</strong> — splits content into semantic blocks (functions, classes, paragraphs).</li>
          <li><strong>Semantic dedup</strong> — TF-IDF scoring removes near-duplicate chunks.</li>
          <li><strong>Density scoring</strong> — ranks remaining chunks by information density.</li>
          <li><strong>Budget selection</strong> — keeps the highest-value chunks until the token budget is hit.</li>
        </ol>
      </section>

      <section className="doc-section">
        <h2>API reference</h2>
        <div className="endpoint-list">
          <div className="endpoint-row">
            <span className="method">POST</span>
            <code>/compress</code>
            <span className="desc">Compress raw text</span>
          </div>
          <div className="endpoint-row">
            <span className="method">POST</span>
            <code>/compress/file</code>
            <span className="desc">Upload and compress a file</span>
          </div>
          <div className="endpoint-row">
            <span className="method">POST</span>
            <code>/compress/diff</code>
            <span className="desc">Compress a manual unified diff</span>
          </div>
          <div className="endpoint-row">
            <span className="method">POST</span>
            <code>/compress/diff/github</code>
            <span className="desc">Compress a GitHub PR diff</span>
          </div>
          <div className="endpoint-row">
            <span className="method">GET</span>
            <code>/presets</code>
            <span className="desc">List compression presets</span>
          </div>
          <div className="endpoint-row">
            <span className="method">GET</span>
            <code>/health</code>
            <span className="desc">Health check</span>
          </div>
        </div>
      </section>

      <section className="doc-section">
        <h2>Accuracy evaluation</h2>
        <p>
          The frontend reports structural and token-level stats. Real downstream LLM accuracy retention
          requires <code>eval_harness.py</code> — wire it up separately if you need live accuracy scores.
        </p>
      </section>
    </div>
  )
}
