import type { DashboardPayloadDTO } from "../../types/api";

export function OverviewPanel({ dashboard }: { dashboard: DashboardPayloadDTO }) {
  return <div className="empty-state">OverviewPanel compatibility wrapper for {dashboard.overview.signal_key}.</div>;
}
