import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { FileJson, RefreshCw, SlidersHorizontal } from "lucide-react";
import { DashboardSectionRenderer } from "../components/DashboardSectionRenderer";
import { DashboardTabs, normalizeDashboardTab } from "../components/DashboardTabs";
import { MetricCard } from "../components/MetricCard";
import { StatusBadge } from "../components/StatusBadge";
import { getRunDashboard } from "../lib/api";
import type { DashboardPayloadDTO } from "../types/api";

function formatDateTime(value?: string | null) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString();
}

export function RunDetailPage() {
  const { runId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [dashboard, setDashboard] = useState<DashboardPayloadDTO | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const payload = await getRunDashboard(runId);
      setDashboard(payload);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [runId]);

  const tabs = dashboard?.tabs ?? [];
  const activeTab = useMemo(() => normalizeDashboardTab(searchParams.get("tab"), tabs), [searchParams, tabs]);
  const activeTabPayload = tabs.find((tab) => tab.tab_key === activeTab) ?? tabs[0];

  if (loading) {
    return <div className="empty-state">Loading dashboard...</div>;
  }

  if (error || !dashboard) {
    return <div className="error-state">{error ?? "Dashboard unavailable"}</div>;
  }

  function handleTabChange(tab: string) {
    setSearchParams(tab === tabs[0]?.tab_key ? {} : { tab });
  }

  return (
    <div className="page">
      <header className="page-hero detail-hero">
        <div>
          <p className="eyebrow">Signal Detail</p>
          <h2>{dashboard.overview.signal_key}</h2>
          <p className="page-copy">
            {dashboard.overview.requested_start_date} to {dashboard.overview.requested_end_date}
          </p>
        </div>
        <div className="hero-actions">
          <StatusBadge status={dashboard.overview.status} />
          <button onClick={() => void load()}>
            <RefreshCw size={17} aria-hidden="true" />
            Refresh
          </button>
          <Link to={`/runs/${runId}?tab=sensitivity`} className="button-link">
            <SlidersHorizontal size={17} aria-hidden="true" />
            Sensitivity
          </Link>
        </div>
      </header>

      <section className="research-console" aria-label="Run research console">
        <div className="console-snapshot">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Overview</p>
              <h2>Run Snapshot</h2>
            </div>
          </div>
          <div className="overview-grid">
            <div>
              <span>Run ID</span>
              <strong>{dashboard.run.run_id}</strong>
            </div>
            <div>
              <span>Created</span>
              <strong>{formatDateTime(dashboard.overview.created_at)}</strong>
            </div>
            <div>
              <span>Finished</span>
              <strong>{formatDateTime(dashboard.overview.finished_at)}</strong>
            </div>
            <div>
              <span>Source</span>
              <strong>{dashboard.overview.source_type}</strong>
            </div>
          </div>
        </div>

        <section className="metric-grid console-metrics">
          {dashboard.key_metrics.map((metric) => (
            <MetricCard key={metric.metric_key} metric={metric} />
          ))}
        </section>

        {tabs.length > 0 ? <DashboardTabs tabs={tabs} activeTab={activeTab} onChange={handleTabChange} /> : null}
      </section>

      <div className="tab-stack">
        {activeTabPayload?.sections.map((section) => (
          <DashboardSectionRenderer key={section.section_key} section={section} />
        ))}
        {tabs.length === 0 ? <div className="empty-state">No dashboard sections available for this run.</div> : null}
      </div>

      <details className="panel secondary-panel">
        <summary>
          <span>
            <p className="eyebrow">Config</p>
            <strong>Run Parameters</strong>
          </span>
        </summary>
        <pre className="config-block">{JSON.stringify(dashboard.config_summary.config, null, 2)}</pre>
      </details>

      <details className="panel secondary-panel">
        <summary>
          <span>
            <p className="eyebrow">Artifacts</p>
            <strong>Output Files</strong>
          </span>
        </summary>
        <div className="artifact-list">
          {dashboard.artifacts.map((artifact) => (
            <a key={artifact.artifact_key} className="artifact-item" href={artifact.uri} target="_blank" rel="noreferrer">
              <FileJson size={18} aria-hidden="true" />
              <strong>{artifact.payload.label ? String(artifact.payload.label) : artifact.artifact_key}</strong>
              <span>{artifact.content_type}</span>
              <span>{artifact.size_bytes} bytes</span>
            </a>
          ))}
        </div>
      </details>
    </div>
  );
}
