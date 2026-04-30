import { PlotlyChart } from "./PlotlyChart";
import type { DashboardNamedSeriesDTO } from "../../types/api";

export function TimeseriesPanel({ title, eyebrow, series }: { title: string; eyebrow?: string; series: DashboardNamedSeriesDTO[] }) {
  if (series.length === 0) {
    return <div className="empty-state compact">No timeseries data.</div>;
  }
  return (
    <section className="panel chart-panel">
      <div className="panel-header">
        <div>
          {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
          <h2>{title}</h2>
        </div>
      </div>
      <PlotlyChart
        data={series.map((item) => ({
          type: "scatter",
          mode: "lines",
          name: item.label,
          x: item.points.map((point) => point.date),
          y: item.points.map((point) => point.value),
        })) as never[]}
        layout={{ title: { text: title } } as never}
      />
    </section>
  );
}
