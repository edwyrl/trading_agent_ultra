import { CircleHelp } from "lucide-react";
import { MetricCard } from "./MetricCard";
import { PlotlyChart } from "./charts/PlotlyChart";
import type { DashboardMetricCardDTO, DashboardSectionDTO } from "../types/api";

function asNumberArray(value: unknown): number[] {
  return Array.isArray(value) ? value.map((item) => Number(item)).filter((item) => Number.isFinite(item)) : [];
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

type TableColumn = {
  key: string;
  label: string;
};

function asTableColumns(value: unknown): TableColumn[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (typeof item === "string") {
      return [{ key: item, label: item }];
    }
    if (item && typeof item === "object" && "key" in item) {
      const key = String((item as Record<string, unknown>).key ?? "");
      if (!key) {
        return [];
      }
      const labelValue = (item as Record<string, unknown>).label;
      return [{ key, label: String(labelValue ?? key) }];
    }
    return [];
  });
}

function formatMaybePercent(value: unknown, tickFormat?: string) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return String(value ?? "-");
  }
  if (tickFormat?.includes("%")) {
    return `${(numeric * 100).toFixed(1)}%`;
  }
  return `${numeric}`;
}

function renderSection(section: DashboardSectionDTO) {
  const payload = section.payload as Record<string, any>;

  if (section.section_type === "timeseries") {
    const series = Array.isArray(payload.series) ? payload.series : [];
    if (series.length === 0) {
      return <div className="empty-state compact">No timeseries data.</div>;
    }
    const data: any[] = series.map((item: any) => ({
      type: "scatter",
      mode: "lines",
      name: String(item.label ?? item.metric_name ?? "Series"),
      x: Array.isArray(item.points) ? item.points.map((point: any) => String(point.date ?? "")) : [],
      y: Array.isArray(item.points) ? item.points.map((point: any) => Number(point.value ?? 0)) : [],
    }));
    return <PlotlyChart data={data} layout={{ title: { text: section.title }, xaxis: { title: { text: String(payload.x_axis_label ?? "Date") } }, yaxis: { title: { text: String(payload.y_axis_label ?? "Value") }, tickformat: typeof payload.y_tick_format === "string" ? payload.y_tick_format : undefined } } as any} />;
  }

  if (section.section_type === "histogram") {
    const values = asNumberArray(payload.values);
    if (values.length === 0) {
      return <div className="empty-state compact">No distribution data.</div>;
    }
    const threshold = Number(payload.threshold);
    const data: any[] = [
      {
        type: "histogram",
        x: values,
        marker: { color: "rgba(122, 208, 255, 0.72)" },
      },
    ];
    if (Number.isFinite(threshold)) {
      data.push({
        type: "scatter",
        mode: "lines",
        name: "Threshold",
        x: [threshold, threshold],
        y: [0, 1],
        yaxis: "y2",
        line: { color: "#ffd36d", width: 3, dash: "dash" },
      });
    }
    return <PlotlyChart data={data} layout={{ title: { text: section.title }, xaxis: { title: { text: String(payload.x_label ?? "Value") } }, yaxis: { title: { text: String(payload.y_label ?? "Count") } }, yaxis2: { overlaying: "y", visible: false, range: [0, 1] }, bargap: 0.04 } as any} />;
  }

  if (section.section_type === "bar") {
    const categories = asStringArray(payload.categories);
    const series = Array.isArray(payload.series) ? payload.series : [];
    if (categories.length === 0 || series.length === 0) {
      return <div className="empty-state compact">No bar chart data.</div>;
    }
    const data: any[] = series.map((item: any) => ({
      type: "bar",
      name: String(item.label ?? "Series"),
      x: categories,
      y: asNumberArray(item.values),
      marker: item.colors ? { color: item.colors } : { color: item.color ?? "#7ad0ff" },
      error_y: Array.isArray(item.error_values)
        ? {
            type: "data",
            array: asNumberArray(item.error_values),
            visible: true,
          }
        : undefined,
    }));
    return <PlotlyChart data={data} layout={{ title: { text: section.title }, barmode: String(payload.mode ?? "group"), xaxis: { title: { text: String(payload.x_label ?? "Category") } }, yaxis: { title: { text: String(payload.y_label ?? "Value") }, tickformat: typeof payload.y_tick_format === "string" ? payload.y_tick_format : undefined } } as any} />;
  }

  if (section.section_type === "scatter") {
    const traces = Array.isArray(payload.traces) ? payload.traces : [];
    if (traces.length === 0) {
      return <div className="empty-state compact">No scatter data.</div>;
    }
    const data: any[] = traces.map((item: any) => ({
      type: "scatter",
      mode: item.mode ?? "markers",
      name: String(item.label ?? "Series"),
      x: Array.isArray(item.x) ? item.x : [],
      y: Array.isArray(item.y) ? item.y : [],
      showlegend: item.show_legend ?? true,
      marker: item.mode === "markers" ? { color: item.color ?? "#7ad0ff", size: 8 } : undefined,
      line: item.mode === "lines" ? { color: item.color ?? "#7ad0ff", width: Number(item.width ?? 2) } : undefined,
    }));
    return <PlotlyChart data={data} layout={{ title: { text: section.title }, xaxis: { title: { text: String(payload.x_label ?? "X") } }, yaxis: { title: { text: String(payload.y_label ?? "Y") }, tickformat: typeof payload.y_tick_format === "string" ? payload.y_tick_format : undefined }, shapes: Array.isArray(payload.vertical_lines) ? payload.vertical_lines.map((lineValue: any) => ({ type: "line", x0: Number(lineValue), x1: Number(lineValue), y0: 0, y1: 1, yref: "paper", line: { color: "rgba(255, 211, 109, 0.45)", width: 2, dash: "dash" } })) : undefined } as any} />;
  }

  if (section.section_type === "boxplot") {
    const series = Array.isArray(payload.series) ? payload.series : [];
    if (series.length === 0) {
      return <div className="empty-state compact">No boxplot data.</div>;
    }
    const data: any[] = series.map((item: any) => ({
      type: "box",
      name: String(item.label ?? "Series"),
      y: asNumberArray(item.values),
      marker: { color: item.color ?? "#7ad0ff" },
      boxpoints: false,
    }));
    return <PlotlyChart data={data} layout={{ title: { text: section.title }, xaxis: { title: { text: String(payload.x_label ?? "Category") } }, yaxis: { title: { text: String(payload.y_label ?? "Value") }, tickformat: typeof payload.y_tick_format === "string" ? payload.y_tick_format : undefined } } as any} />;
  }

  if (section.section_type === "violin") {
    const series = Array.isArray(payload.series) ? payload.series : [];
    if (series.length === 0) {
      return <div className="empty-state compact">No violin distribution data.</div>;
    }
    const data: any[] = series.flatMap((group: any) => {
      const items = Array.isArray(group.items) ? group.items : [];
      return items.map((item: any) => ({
        type: "violin",
        name: String(group.label ?? "Series"),
        x: asNumberArray(item.values).map(() => String(item.category ?? "")),
        y: asNumberArray(item.values),
        legendgroup: String(group.label ?? "Series"),
        scalegroup: String(item.category ?? ""),
        side: group.side ?? "both",
        line: { color: group.line_color ?? group.color ?? "#7ad0ff" },
        fillcolor: group.color ?? "rgba(122, 208, 255, 0.35)",
        meanline: { visible: true },
        points: false,
        box: { visible: true },
      }));
    });
    return <PlotlyChart className="plotly-wrap tall" data={data} layout={{ title: { text: section.title }, xaxis: { title: { text: String(payload.x_label ?? "Category") } }, yaxis: { title: { text: String(payload.y_label ?? "Value") }, tickformat: typeof payload.y_tick_format === "string" ? payload.y_tick_format : undefined } } as any} />;
  }

  if (section.section_type === "heatmap") {
    const xValues = asNumberArray(payload.x_values);
    const yValues = asNumberArray(payload.y_values);
    const metrics = asStringArray(payload.metrics);
    const cells = Array.isArray(payload.cells) ? payload.cells : [];
    if (xValues.length === 0 || yValues.length === 0 || metrics.length === 0 || cells.length === 0) {
      return <div className="empty-state compact">No sensitivity matrix data.</div>;
    }
    return (
      <div className="chart-grid three-col">
        {metrics.map((metric) => {
          const z = yValues.map((y) =>
            xValues.map((x) => {
              const cell = cells.find((item: any) => Number(item.x_value) === x && Number(item.y_value) === y);
              const metricMap = cell && typeof cell.metrics === "object" && cell.metrics ? cell.metrics : {};
          return Number(metricMap[metric] ?? 0);
            }),
          );
          return <PlotlyChart key={metric} data={[{ type: "heatmap", x: xValues, y: yValues, z, colorscale: "YlGnBu", hoverongaps: false, colorbar: { title: metric } }] as any[]} layout={{ title: { text: metric.replace(/_/g, " ") }, xaxis: { title: { text: String(payload.x_key ?? "X") } }, yaxis: { title: { text: String(payload.y_key ?? "Y") } } } as any} />;
        })}
      </div>
    );
  }

  if (section.section_type === "stat_cards") {
    const cards = Array.isArray(payload.cards) ? (payload.cards as DashboardMetricCardDTO[]) : [];
    if (cards.length === 0) {
      return <div className="empty-state compact">No summary cards.</div>;
    }
    return (
      <div className="metric-grid">
        {cards.map((card) => (
          <MetricCard key={card.metric_key} metric={card} />
        ))}
      </div>
    );
  }

  if (section.section_type === "table") {
    const columns = asTableColumns(payload.columns);
    const rows = Array.isArray(payload.rows) ? payload.rows : [];
    if (columns.length === 0 || rows.length === 0) {
      return <div className="empty-state compact">No table rows.</div>;
    }
    return (
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key}>{column.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              const item = row as Record<string, unknown>;
              return (
                <tr key={`${section.section_key}-${index}`}>
                  {columns.map((column) => (
                    <td key={column.key}>
                      {formatMaybePercent(item[column.key], typeof payload.y_tick_format === "string" ? payload.y_tick_format : undefined)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  if (section.section_type === "markdown" || section.section_type === "text") {
    return <div className="section-copy">{String(payload.text ?? payload.markdown ?? "")}</div>;
  }

  return <div className="empty-state compact">Unsupported section type: {section.section_type}</div>;
}

export function DashboardSectionRenderer({ section }: { section: DashboardSectionDTO }) {
  const summary = describeSection(section);
  const helpText = describeSectionMeaning(section);
  return (
    <section className="panel chart-panel">
      <div className="panel-header">
        <div>
          {section.eyebrow ? <p className="eyebrow">{section.eyebrow}</p> : null}
          <div className="section-heading-row">
            <h2>{section.title}</h2>
            <button type="button" className="chart-help" aria-label={`Explain ${section.title}`}>
              <CircleHelp size={16} aria-hidden="true" />
              <span className="chart-help-copy" role="tooltip">
                {helpText}
              </span>
            </button>
          </div>
          {summary ? <p className="section-meta">{summary}</p> : null}
        </div>
      </div>
      {renderSection(section)}
    </section>
  );
}

function describeSection(section: DashboardSectionDTO) {
  const payload = section.payload as Record<string, any>;
  if (section.section_type === "timeseries") {
    const series = Array.isArray(payload.series) ? payload.series : [];
    const points = series.reduce((count: number, item: any) => count + (Array.isArray(item.points) ? item.points.length : 0), 0);
    return `${series.length} series · ${points} points`;
  }
  if (section.section_type === "histogram") {
    return `${asNumberArray(payload.values).length} observations`;
  }
  if (section.section_type === "violin" || section.section_type === "boxplot") {
    const series = Array.isArray(payload.series) ? payload.series : [];
    const observations = series.reduce((count: number, item: any) => {
      if (Array.isArray(item.values)) {
        return count + item.values.length;
      }
      if (Array.isArray(item.items)) {
        return count + item.items.reduce((inner: number, child: any) => inner + asNumberArray(child.values).length, 0);
      }
      return count;
    }, 0);
    return `${observations} observations · distribution view`;
  }
  if (section.section_type === "heatmap") {
    const xCount = asNumberArray(payload.x_values).length;
    const yCount = asNumberArray(payload.y_values).length;
    const metrics = asStringArray(payload.metrics);
    return `${xCount * yCount} cells · ${metrics.length} metrics · hover for exact values`;
  }
  if (section.section_type === "table") {
    const rows = Array.isArray(payload.rows) ? payload.rows.length : 0;
    return `${rows} rows`;
  }
  return "";
}

function describeSectionMeaning(section: DashboardSectionDTO) {
  if (section.section_type === "timeseries") {
    return "A timeseries chart shows how one or more metrics evolve across time, making trend, turning-point, and regime changes easier to spot.";
  }
  if (section.section_type === "histogram") {
    return "A histogram groups values into bins so you can see how often different ranges occur and whether the distribution is skewed, concentrated, or extreme.";
  }
  if (section.section_type === "bar") {
    return "A bar chart compares magnitudes across categories or horizons, helping you quickly judge relative strength, ranking, and directional differences.";
  }
  if (section.section_type === "scatter") {
    return "A scatter chart shows individual observations or paths. It is useful for spotting dispersion, clusters, outliers, and event-by-event variability.";
  }
  if (section.section_type === "boxplot") {
    return "A boxplot summarizes a distribution with median, spread, and tails, making it useful for comparing typical outcomes and outlier risk across groups.";
  }
  if (section.section_type === "violin") {
    return "A violin chart shows the full shape of a distribution, including where values are dense or sparse, so you can compare outcome profiles beyond the mean.";
  }
  if (section.section_type === "heatmap") {
    return "A heatmap encodes values by color across a two-dimensional grid, which is useful for parameter sweeps and for locating stable or fragile regions.";
  }
  if (section.section_type === "stat_cards") {
    return "Stat cards highlight the headline metrics for a run, giving a compact snapshot of the most important current values before deeper analysis.";
  }
  if (section.section_type === "table") {
    return "A table presents exact underlying values row by row, which is useful when you need precision, detailed inspection, or to verify what a chart summarizes.";
  }
  return "This panel provides supporting context for the run and helps interpret the surrounding charts or outputs.";
}
