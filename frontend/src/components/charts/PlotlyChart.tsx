import Plot from "react-plotly.js";
import type { Config, Data, Layout } from "plotly.js";

const BASE_LAYOUT: Partial<Layout> = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(8, 15, 26, 0.72)",
  font: { color: "#e7eefb", family: "Fira Sans, Avenir Next, Segoe UI, sans-serif" },
  margin: { l: 52, r: 24, t: 48, b: 48 },
  xaxis: { gridcolor: "rgba(114, 132, 163, 0.2)", zerolinecolor: "rgba(238, 244, 255, 0.28)" },
  yaxis: { gridcolor: "rgba(114, 132, 163, 0.2)", zerolinecolor: "rgba(238, 244, 255, 0.28)" },
  legend: { orientation: "h", y: -0.2, font: { size: 12 } },
  hoverlabel: { bgcolor: "#111a2b", bordercolor: "#2f81f7", font: { color: "#f7fbff" } },
};

const BASE_CONFIG: Partial<Config> = {
  displayModeBar: false,
  responsive: true,
};

interface PlotlyChartProps {
  data: Data[];
  layout?: Partial<Layout>;
  className?: string;
}

export function PlotlyChart({ data, layout, className = "plotly-wrap" }: PlotlyChartProps) {
  return (
    <div className={className}>
      <Plot
        data={data}
        layout={{ ...BASE_LAYOUT, ...layout, autosize: true }}
        config={BASE_CONFIG}
        useResizeHandler
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
}
