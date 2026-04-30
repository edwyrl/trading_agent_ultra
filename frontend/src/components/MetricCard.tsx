import { ArrowDownRight, ArrowUpRight, Gauge } from "lucide-react";
import type { DashboardMetricCardDTO } from "../types/api";

export function MetricCard({ metric }: { metric: DashboardMetricCardDTO }) {
  const value = Number(metric.value);
  const tone = inferTone(metric.metric_key, value);
  const Icon = tone === "positive" ? ArrowUpRight : tone === "negative" ? ArrowDownRight : Gauge;

  return (
    <article className={`metric-card metric-card-${tone}`}>
      <div className="metric-card-top">
        <p className="metric-label">{metric.label}</p>
        <span className="metric-icon" aria-hidden="true">
          <Icon size={18} />
        </span>
      </div>
      <h3>{metric.display || metric.value}</h3>
      <p className="metric-key">{metric.metric_key}</p>
    </article>
  );
}

function inferTone(metricKey: string, value: number) {
  const key = metricKey.toLowerCase();
  if (key.includes("risk") || key.includes("failed")) {
    return value >= 70 ? "negative" : value >= 40 ? "warning" : "positive";
  }
  if (key.includes("alpha") || key.includes("return")) {
    return value > 0 ? "positive" : value < 0 ? "negative" : "neutral";
  }
  if (key.includes("event") || key.includes("signal")) {
    return value > 0 ? "warning" : "neutral";
  }
  return "neutral";
}
