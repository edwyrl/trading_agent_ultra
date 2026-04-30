import type { DashboardPayloadDTO } from "../../types/api";

export function CurrentRegimePanel({ dashboard }: { dashboard: DashboardPayloadDTO }) {
  return <div className="empty-state">CurrentRegimePanel compatibility wrapper for {dashboard.overview.signal_key}.</div>;
}
