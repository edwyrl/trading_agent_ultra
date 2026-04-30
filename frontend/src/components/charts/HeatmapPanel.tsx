import { useMemo, useState } from "react";

interface HeatmapPanelProps {
  sensitivity: {
    x_key: string;
    y_key: string;
    x_values: number[];
    y_values: number[];
    metrics: string[];
    cells: Array<{
      x_value: number;
      y_value: number;
      metrics: Record<string, number>;
    }>;
  };
}

export function HeatmapPanel({ sensitivity }: HeatmapPanelProps) {
  const [metric, setMetric] = useState(sensitivity.metrics[0] ?? "value");
  const cellMap = useMemo(() => {
    const map = new Map<string, number>();
    for (const cell of sensitivity.cells) {
      map.set(`${cell.x_value}:${cell.y_value}`, cell.metrics[metric] ?? 0);
    }
    return map;
  }, [metric, sensitivity.cells]);

  return (
    <section className="panel chart-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Sensitivity</p>
          <h2>Parameter Heatmap</h2>
        </div>
        <label>
          Sensitivity metric
          <select aria-label="Sensitivity metric" value={metric} onChange={(event) => setMetric(event.target.value)}>
            {sensitivity.metrics.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="heatmap-grid" role="grid">
        <div className="heatmap-row">
          <div className="heatmap-corner">
            {sensitivity.y_key} \ {sensitivity.x_key}
          </div>
          {sensitivity.x_values.map((value) => (
            <div key={`x-${value}`} className="heatmap-axis">
              {value}
            </div>
          ))}
        </div>
        {sensitivity.y_values.map((y) => (
          <div key={`row-${y}`} className="heatmap-row">
            <div className="heatmap-axis">{y}</div>
            {sensitivity.x_values.map((x) => (
              <div key={`${x}-${y}`} className="heatmap-cell">
                {cellMap.get(`${x}:${y}`)?.toFixed(3) ?? "0.000"}
              </div>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
