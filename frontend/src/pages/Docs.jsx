import { useScrollReveal } from '../hooks/useApi.js'

export default function Docs() {
  const s1 = useScrollReveal()
  const s2 = useScrollReveal()
  const s3 = useScrollReveal()
  const s4 = useScrollReveal()
  const s5 = useScrollReveal()
  const s6 = useScrollReveal()

  return (
    <div className="page docs-page">
      <h1>Documentation</h1>

      <section className="doc-section glass" ref={s1}>
        <h2>What is Context Compress?</h2>
        <p>Context Compress is a preprocessing tool that reduces the size of long text, code, and log contexts before they are sent to a large language model. By removing redundancy and low-signal content, it lowers token usage, cuts API costs, and speeds up inference — all while preserving the information the model actually needs to answer accurately.</p>
      </section>

      <section className="doc-section glass" ref={s2}>
        <h2>How it works</h2>
        <p>The compressor runs your input through a multi-stage pipeline designed to maximize information density:</p>
        <ol className="pipeline-list">
          <li><strong>Structural analysis</strong> — identifies and collapses redundant formatting, imports, and boilerplate.</li>
          <li><strong>Semantic chunking</strong> — splits content into meaningful blocks (functions, paragraphs, log entries).</li>
          <li><strong>Deduplication</strong> — scores chunks for uniqueness and removes near-duplicates.</li>
          <li><strong>Density ranking</strong> — keeps the highest-value chunks within your target token budget.</li>
          <li><strong>Dependency preservation</strong> — ensures no function or definition is dropped if another kept block still references it.</li>
        </ol>
      </section>

      <section className="doc-section glass" ref={s3}>
        <h2>Supported inputs</h2>
        <ul className="plain-list">
          <li>Raw text, code, logs, or prose pasted directly into the editor</li>
          <li>File uploads — .txt, .log, .py, .js, .md, .json, .csv, and more</li>
          <li>Unified diff files or patches for manual review</li>
          <li>GitHub pull request URLs for automatic diff fetching</li>
        </ul>
      </section>

      <section className="doc-section glass" ref={s4}>
        <h2>Compression presets</h2>
        <p>Choose a preset that matches your risk tolerance:</p>
        <ul className="plain-list">
          <li><strong>Conservative</strong> — light trim, accuracy-first approach</li>
          <li><strong>Balanced</strong> — the default trade-off between size and fidelity</li>
          <li><strong>Aggressive</strong> — maximum reduction for cost-sensitive workloads</li>
          <li><strong>Custom</strong> — dial in your own target reduction percentage</li>
        </ul>
      </section>

      <section className="doc-section glass" ref={s5}>
        <h2>Model selection</h2>
        <p>Picking a target model changes the tokenizer used to count tokens, so your before/after numbers reflect that model's real token economics. Supported profiles include OpenAI's GPT-4 and GPT-4o families, as well as approximations for Claude and Gemini.</p>
      </section>

      <section className="doc-section glass" ref={s6}>
        <h2>Privacy & security</h2>
        <p>All compression happens server-side over an encrypted connection. We do not store your inputs or outputs beyond the duration of the request. For sensitive code, you may run the compressor in a self-hosted environment.</p>
      </section>
    </div>
  )
}
