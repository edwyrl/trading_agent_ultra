import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BarChart3, Plus, RefreshCw, SearchX, Square, Trash2 } from "lucide-react";
import { cancelRun, createRun, deleteRun, listPlugins, listRuns } from "../lib/api";
import { NewRunPanel } from "../components/NewRunPanel";
import { StatusBadge } from "../components/StatusBadge";
import type { SignalPluginMetaDTO, SignalRunRequestDTO, SignalRunStatus, SignalRunStatusDTO } from "../types/api";

const FILTERS: Array<SignalRunStatus | "ALL"> = ["ALL", "PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED"];
const TERMINAL_STATUSES: SignalRunStatus[] = ["SUCCEEDED", "FAILED", "CANCELED"];

export function RunsPage() {
  const [runs, setRuns] = useState<SignalRunStatusDTO[]>([]);
  const [plugins, setPlugins] = useState<SignalPluginMetaDTO[]>([]);
  const [statusFilter, setStatusFilter] = useState<SignalRunStatus | "ALL">("ALL");
  const [showNewRunPanel, setShowNewRunPanel] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorTitle, setErrorTitle] = useState<string>("Unable to load signal runs");
  const [error, setError] = useState<string | null>(null);
  const [busyRunId, setBusyRunId] = useState<string | null>(null);

  async function load(filter: SignalRunStatus | "ALL" = statusFilter) {
    setLoading(true);
    setErrorTitle("Unable to load signal runs");
    setError(null);
    try {
      const [runsValue, pluginsValue] = await Promise.all([
        listRuns(filter === "ALL" ? undefined : filter),
        listPlugins(),
      ]);
      setRuns(runsValue);
      setPlugins(pluginsValue);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [statusFilter]);

  async function handleCreateRun(request: SignalRunRequestDTO) {
    const created = await createRun(request);
    setSuccessMessage(`Queued ${created.run_id.slice(0, 24)}...`);
    setError(null);
    setStatusFilter("ALL");
    setShowNewRunPanel(false);
    await load("ALL");
  }

  async function handleCancel(run: SignalRunStatusDTO) {
    if (!window.confirm(`Stop ${run.run_id}? It will be marked as canceled and removed from active processing.`)) {
      return;
    }
    setBusyRunId(run.run_id);
    setSuccessMessage(null);
    setErrorTitle("Unable to stop run");
    setError(null);
    try {
      await cancelRun(run.run_id);
      setSuccessMessage(`Canceled ${run.run_id.slice(0, 24)}...`);
      await load(statusFilter);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Unknown error");
    } finally {
      setBusyRunId(null);
    }
  }

  async function handleDelete(run: SignalRunStatusDTO) {
    if (!window.confirm(`Delete ${run.run_id}? This removes the run record and its stored signal outputs.`)) {
      return;
    }
    setBusyRunId(run.run_id);
    setSuccessMessage(null);
    setErrorTitle("Unable to delete run");
    setError(null);
    try {
      await deleteRun(run.run_id);
      setSuccessMessage(`Deleted ${run.run_id.slice(0, 24)}...`);
      await load(statusFilter);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Unknown error");
    } finally {
      setBusyRunId(null);
    }
  }

  const pluginMap = new Map(plugins.map((plugin) => [plugin.signal_key, plugin]));
  const statusCounts = FILTERS.filter((filter): filter is SignalRunStatus => filter !== "ALL").map((status) => ({
    status,
    count: runs.filter((run) => run.status === status).length,
  }));
  const totalCount = runs.length;

  return (
    <div className="page">
      <header className="page-hero">
        <div>
          <p className="eyebrow">Task Center</p>
          <h2>Signal Runs</h2>
          <p className="page-copy">Submit experiments, monitor the worker queue, and jump into full research detail.</p>
        </div>
        <div className="hero-actions">
          <button className="primary-action" onClick={() => setShowNewRunPanel(true)}>
            <Plus size={17} aria-hidden="true" />
            New Run
          </button>
          <button onClick={() => void load()} disabled={loading}>
            <RefreshCw size={17} aria-hidden="true" />
            Refresh
          </button>
        </div>
      </header>

      <section className="terminal-summary" aria-label="Run status summary">
        <article>
          <span>Total</span>
          <strong>{totalCount}</strong>
        </article>
        {statusCounts.map((item) => (
          <article key={item.status} className={`summary-${item.status.toLowerCase()}`}>
            <span>{item.status.toLowerCase()}</span>
            <strong>{item.count}</strong>
          </article>
        ))}
      </section>

      <section className="filter-bar" aria-label="Filter runs by status">
        {FILTERS.map((filter) => (
          <button
            key={filter}
            type="button"
            className={`filter-pill${statusFilter === filter ? " active" : ""}`}
            aria-pressed={statusFilter === filter}
            onClick={() => setStatusFilter(filter)}
          >
            {filter === "ALL" ? "All Runs" : filter}
          </button>
        ))}
      </section>

      {successMessage ? <div className="success-state" role="status">{successMessage}</div> : null}
      {showNewRunPanel ? (
        <NewRunPanel
          plugins={plugins}
          onCancel={() => setShowNewRunPanel(false)}
          onSubmit={handleCreateRun}
        />
      ) : null}
      {loading ? <div className="skeleton-panel">Loading runs...</div> : null}
      {error ? (
        <div className="error-state action-state" role="alert">
          <SearchX size={18} aria-hidden="true" />
          <div>
            <strong>{errorTitle}</strong>
            <p>{error}. Check that the API and worker are healthy, then try again.</p>
          </div>
        </div>
      ) : null}
      {!loading && !error && runs.length === 0 ? (
        <div className="empty-state action-state">
          <BarChart3 size={22} aria-hidden="true" />
          <div>
            <strong>No runs found for this filter.</strong>
            <p>Create a new signal run or switch filters to inspect prior research.</p>
          </div>
          <button className="primary-action" onClick={() => setShowNewRunPanel(true)}>Create first run</button>
        </div>
      ) : null}

      <section className="run-grid">
        {runs.map((run) => (
          <article key={run.run_id} className="run-card">
            <div className="run-card-header">
              <div>
                <p className="run-signal">{pluginMap.get(run.signal_key)?.name ?? run.signal_key}</p>
                <h3>{run.run_id.slice(0, 18)}...</h3>
              </div>
              <StatusBadge status={run.status} />
            </div>
            <div className="run-meta">
              <span>{run.requested_start_date} to {run.requested_end_date}</span>
              <span>{run.source_type}</span>
              <span>Updated {formatShortDateTime(run.updated_at)}</span>
            </div>
            <dl className="run-summary">
              <div>
                <dt>Events</dt>
                <dd>{String(run.summary.event_count ?? "-")}</dd>
              </div>
              <div>
                <dt>Signals</dt>
                <dd>{String(run.summary.signal_day_count ?? "-")}</dd>
              </div>
              <div>
                <dt>Risk</dt>
                <dd>{String(run.summary.headline_metric_display ?? run.summary.latest_expanding_pct ?? "-")}</dd>
              </div>
            </dl>
            {run.error ? <p className="run-error">{run.error}</p> : null}
            <div className="card-actions">
              <Link to={`/runs/${run.run_id}`}>Open detail</Link>
              <Link to={`/runs/${run.run_id}/compare`}>Compare params</Link>
              {TERMINAL_STATUSES.includes(run.status) ? (
                <button
                  type="button"
                  className="danger-action"
                  disabled={busyRunId === run.run_id}
                  aria-label={`Delete run ${run.run_id}`}
                  onClick={() => void handleDelete(run)}
                >
                  <Trash2 size={15} aria-hidden="true" />
                  Delete
                </button>
              ) : (
                <button
                  type="button"
                  className="warning-action"
                  disabled={busyRunId === run.run_id}
                  aria-label={`Stop run ${run.run_id}`}
                  onClick={() => void handleCancel(run)}
                >
                  <Square size={15} aria-hidden="true" />
                  Stop
                </button>
              )}
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}

function formatShortDateTime(value?: string | null) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString(undefined, { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
