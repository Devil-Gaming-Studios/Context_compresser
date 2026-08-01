import { useNavigate } from 'react-router-dom'

export default function Home() {
  const navigate = useNavigate()

  return (
    <div className="page home-page">
      <section className="hero">
        <h1 className="hero-title">
          Strip repetitive syntax and filler from long contexts
          <br />
          <span className="hero-accent">before they hit the model</span>
        </h1>
        <div className="hero-stats">
          <div className="hero-stat">
            <span className="hero-stat-value">&gt;70%</span>
            <span className="hero-stat-label">size reduction</span>
          </div>
          <div className="hero-stat">
            <span className="hero-stat-value">95%+</span>
            <span className="hero-stat-label">accuracy retention</span>
          </div>
        </div>
        <div className="hero-ctas">
          <button className="btn-primary" onClick={() => navigate('/app')}>
            Start compressing →
          </button>
          <button className="btn-ghost" onClick={() => navigate('/docs')}>
            How it works
          </button>
        </div>
      </section>

      <section className="feature-grid">
        <div className="feature-card">
          <div className="feature-icon">⊜</div>
          <h3>Semantic deduplication</h3>
          <p>TF-IDF near-duplicate removal eliminates repeated boilerplate across chunks without losing unique signal.</p>
        </div>
        <div className="feature-card">
          <div className="feature-icon">⊟</div>
          <h3>Structural stripping</h3>
          <p>Collapses redundant structural lines — imports, closing braces, decorative comments — while preserving semantics.</p>
        </div>
        <div className="feature-card">
          <div className="feature-icon">⊡</div>
          <h3>Dependency-aware chunking</h3>
          <p>Never drops a function another kept block still calls. The compressor builds a dependency graph before cutting.</p>
        </div>
        <div className="feature-card">
          <div className="feature-icon">⊞</div>
          <h3>Diff-aware PR compression</h3>
          <p>Compresses GitHub PR diffs by keeping changed blocks and restoring only the dependencies they touch.</p>
        </div>
      </section>

      <section className="metrics-section">
        <h2>Evaluation metrics</h2>
        <div className="metrics-grid">
          <div className="metric">
            <span className="metric-name">Compression ratio</span>
            <span className="metric-desc">How much smaller the output is versus the input, measured in tokens.</span>
          </div>
          <div className="metric">
            <span className="metric-name">Cost reduction</span>
            <span className="metric-desc">Estimated API cost savings based on the target model's per-token pricing.</span>
          </div>
          <div className="metric">
            <span className="metric-name">Accuracy retention</span>
            <span className="metric-desc">Structural and semantic fidelity score. Real downstream LLM eval available via <code>eval_harness.py</code>.</span>
          </div>
          <div className="metric">
            <span className="metric-name">Latency speedup</span>
            <span className="metric-desc">Time saved on inference due to shorter prompt length.</span>
          </div>
        </div>
      </section>
    </div>
  )
}
