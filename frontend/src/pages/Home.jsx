import { useNavigate } from 'react-router-dom'
import { useScrollReveal } from '../hooks/useApi.js'

export default function Home() {
  const navigate = useNavigate()
  const heroRef = useScrollReveal()
  const featuresRef = useScrollReveal()
  const metricsRef = useScrollReveal()
  const ctaRef = useScrollReveal()

  return (
    <div className="page home-page">
      <section className="hero" ref={heroRef}>
        <div className="hero-badge glass-pill">✦ Context Compress</div>
        <h1 className="hero-title">
          Shrink long contexts.<br />
          <span className="gradient-text">Keep every insight.</span>
        </h1>
        <p className="hero-sub">
          Strip repetitive syntax and filler from code, logs, and documents
          before they reach your LLM — so you pay less and get more.
        </p>
        <div className="hero-ctas">
          <button className="btn btn-primary btn-lg" onClick={() => navigate('/app')}>
            Start compressing →
          </button>
          <button className="btn btn-ghost btn-lg" onClick={() => navigate('/docs')}>
            Learn more
          </button>
        </div>
        <div className="hero-stats-row">
          <div className="hero-stat glass"><span className="hero-stat-value">&gt;70%</span><span className="hero-stat-label">smaller prompts</span></div>
          <div className="hero-stat glass"><span className="hero-stat-value">95%+</span><span className="hero-stat-label">accuracy retained</span></div>
          <div className="hero-stat glass"><span className="hero-stat-value">3×</span><span className="hero-stat-label">faster inference</span></div>
        </div>
      </section>

      <section className="features-section" ref={featuresRef}>
        <h2 className="section-title">How it works</h2>
        <div className="feature-grid">
          <div className="feature-card glass glass-hover"><div className="feature-icon">⊜</div><h3>Semantic deduplication</h3><p>Near-duplicate removal powered by TF-IDF scoring eliminates repeated boilerplate without losing unique signal.</p></div>
          <div className="feature-card glass glass-hover"><div className="feature-icon">⊟</div><h3>Structural stripping</h3><p>Collapses redundant imports, closing braces, and decorative comments while preserving meaning.</p></div>
          <div className="feature-card glass glass-hover"><div className="feature-icon">⊡</div><h3>Dependency awareness</h3><p>Builds a call-graph before cutting — never drops a function another kept block still references.</p></div>
          <div className="feature-card glass glass-hover"><div className="feature-icon">⊞</div><h3>Diff-aware PR compression</h3><p>Compress GitHub PR diffs by keeping changed blocks and restoring only the dependencies they touch.</p></div>
        </div>
      </section>

      <section className="metrics-section" ref={metricsRef}>
        <h2 className="section-title">Built for real results</h2>
        <div className="metrics-grid">
          <div className="metric-card glass glass-hover"><span className="metric-name">Compression ratio</span><span className="metric-desc">Measure how much smaller your output is versus the input, in real tokens.</span></div>
          <div className="metric-card glass glass-hover"><span className="metric-name">Cost reduction</span><span className="metric-desc">See estimated API savings based on your target model's per-token pricing.</span></div>
          <div className="metric-card glass glass-hover"><span className="metric-name">Accuracy retention</span><span className="metric-desc">Structural and semantic fidelity scoring ensures nothing important is lost.</span></div>
          <div className="metric-card glass glass-hover"><span className="metric-name">Latency speedup</span><span className="metric-desc">Shorter prompts mean faster time-to-first-token from your LLM provider.</span></div>
        </div>
      </section>

      <section className="cta-section" ref={ctaRef}>
        <div className="cta-card glass glass-hover">
          <h2>Ready to compress?</h2>
          <p>Drop in code, logs, or a PR diff and see the difference in seconds.</p>
          <button className="btn btn-primary btn-lg" onClick={() => navigate('/app')}>Open the workspace →</button>
        </div>
      </section>
    </div>
  )
}
