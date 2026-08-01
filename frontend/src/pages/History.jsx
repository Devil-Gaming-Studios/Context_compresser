import { useHistory } from '../hooks/useApi.js'

export default function History() {
  const { data: jobs, loading, error } = useHistory()

  return (
    <div className="page history-page">
      <header className="page-header">
        <h1>History</h1>
        <p className="subtitle">Recent compression jobs and their results</p>
      </header>

      {loading && <div className="skeleton-list" />}
      {error && <div className="alert error">{error}</div>}

      {!loading && !error && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Time</th>
                <th>Input</th>
                <th>Output</th>
                <th>Ratio</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {jobs?.length === 0 && (
                <tr>
                  <td colSpan={6} className="empty-cell">
                    No jobs yet. Go to Compress to start one.
                  </td>
                </tr>
              )}
              {jobs?.map((job) => (
                <tr key={job.id}>
                  <td className="mono">{job.id.slice(0, 8)}</td>
                  <td>{new Date(job.createdAt).toLocaleString()}</td>
                  <td>{job.inputLength?.toLocaleString()} chars</td>
                  <td>{job.outputLength?.toLocaleString()} chars</td>
                  <td className="mono">{job.ratio}%</td>
                  <td>
                    <span className={`status-pill ${job.status}`}>
                      {job.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
