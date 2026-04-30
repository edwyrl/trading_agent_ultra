import React from "react";
import { render, screen } from "@testing-library/react";
import { HeatmapPanel } from "./HeatmapPanel";

test("heatmap panel renders metric selector and cells", () => {
  render(
    <HeatmapPanel
      sensitivity={{
        x_key: "top_pct",
        y_key: "threshold",
        x_values: [0.05, 0.1],
        y_values: [0.45],
        metrics: ["alpha", "freq"],
        cells: [
          { x_value: 0.05, y_value: 0.45, metrics: { alpha: -0.02, freq: 0.1 } },
          { x_value: 0.1, y_value: 0.45, metrics: { alpha: 0.03, freq: 0.2 } },
        ],
      }}
    />,
  );

  expect(screen.getByLabelText("Sensitivity metric")).toBeInTheDocument();
  expect(screen.getByRole("grid")).toBeInTheDocument();
  expect(screen.getByText("-0.020")).toBeInTheDocument();
});
