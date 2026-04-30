import React from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { RunDetailPage } from "./RunDetailPage";

vi.mock("../lib/api", () => ({
  getRunDashboard: vi.fn(async () => ({
    run: {
      run_id: "signal-run:test",
      signal_key: "market_breadth_crowding",
      source_type: "POSTGRES",
      status: "SUCCEEDED",
      requested_start_date: "2026-04-01",
      requested_end_date: "2026-04-20",
      created_at: "2026-04-20T00:00:00Z",
      updated_at: "2026-04-20T00:00:00Z",
      config: {},
      summary: {},
    },
    overview: {
      signal_key: "market_breadth_crowding",
      source_type: "POSTGRES",
      status: "SUCCEEDED",
      requested_start_date: "2026-04-01",
      requested_end_date: "2026-04-20",
      created_at: "2026-04-20T00:00:00Z",
      updated_at: "2026-04-20T00:00:00Z",
      started_at: "2026-04-20T00:01:00Z",
      finished_at: "2026-04-20T00:02:00Z",
    },
    config_summary: {
      signal_key: "market_breadth_crowding",
      source_type: "POSTGRES",
      date_range: { start_date: "2026-04-01", end_date: "2026-04-20" },
      config: { threshold: 0.7 },
    },
    key_metrics: [{ metric_key: "risk_score", label: "Risk Score", value: 62, unit: "", display: "62" }],
    tabs: [
      {
        tab_key: "overview",
        label: "Overview",
        sections: [
          {
            section_key: "crowding-vs-market",
            title: "Crowding Score vs All A-share Return Proxy",
            section_type: "timeseries",
            eyebrow: "Overview",
            payload: {
              series: [
                {
                  label: "Crowding Score",
                  points: [
                    { date: "2026-04-01", value: 0.4 },
                    { date: "2026-04-02", value: 0.5 },
                  ],
                },
              ],
            },
          },
          {
            section_key: "snapshot-table",
            title: "Latest Snapshot",
            section_type: "table",
            eyebrow: "Snapshot",
            payload: {
              columns: [
                { key: "ts_code", label: "Ticker" },
                { key: "crowding_score", label: "Crowding Score" },
              ],
              rows: [{ ts_code: "000001.SZ", crowding_score: 0.88 }],
            },
          },
        ],
      },
      {
        tab_key: "breadth",
        label: "Breadth",
        sections: [
          {
            section_key: "breadth-balance",
            title: "Advance / Decline Balance",
            section_type: "timeseries",
            eyebrow: "Breadth",
            payload: {
              series: [
                {
                  label: "Advance Ratio",
                  points: [
                    { date: "2026-04-01", value: 0.55 },
                    { date: "2026-04-02", value: 0.61 },
                  ],
                },
              ],
            },
          },
        ],
      },
      {
        tab_key: "sensitivity",
        label: "Sensitivity",
        sections: [
          {
            section_key: "breadth-sensitivity",
            title: "Threshold vs Consecutive Days",
            section_type: "heatmap",
            eyebrow: "Sensitivity",
            payload: {
              x_key: "threshold",
              y_key: "consecutive_days",
              x_values: [0.6, 0.7],
              y_values: [1, 2],
              metrics: ["alpha", "win_rate", "freq"],
              cells: [
                { x_value: 0.6, y_value: 1, metrics: { alpha: 0.01, win_rate: 0.55, freq: 0.2 } },
                { x_value: 0.7, y_value: 2, metrics: { alpha: -0.02, win_rate: 0.48, freq: 0.1 } },
              ],
            },
          },
        ],
      },
    ],
    artifacts: [
      {
        artifact_type: "json",
        artifact_key: "report",
        uri: "/tmp/report.json",
        content_type: "application/json",
        size_bytes: 100,
        payload: { label: "Research Report" },
      },
    ],
  })),
}));

test("detail page renders generic dashboard tabs and sections", async () => {
  render(
    <MemoryRouter initialEntries={["/runs/signal-run:test"]}>
      <Routes>
        <Route path="/runs/:runId" element={<RunDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

  await waitFor(() => expect(screen.getByText("Run Snapshot")).toBeInTheDocument());
  expect(screen.getByLabelText("Run research console")).toBeInTheDocument();
  expect(screen.getByText("Risk Score")).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("Crowding Score vs All A-share Return Proxy")).toBeInTheDocument();
  expect(screen.getByText("Latest Snapshot")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Explain Latest Snapshot" })).toBeInTheDocument();
  expect(screen.getByText("Ticker")).toBeInTheDocument();
  expect(screen.getByText("000001.SZ")).toBeInTheDocument();
});

test("detail page switches to breadth tab", async () => {
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={["/runs/signal-run:test"]}>
      <Routes>
        <Route path="/runs/:runId" element={<RunDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

  await waitFor(() => expect(screen.getByText("Run Snapshot")).toBeInTheDocument());
  await user.click(screen.getByRole("tab", { name: "Breadth" }));

  expect(await screen.findByText("Advance / Decline Balance")).toBeInTheDocument();
  expect(screen.getAllByTestId("plotly-chart").length).toBeGreaterThanOrEqual(1);
});

test("detail page renders sensitivity tab from query param", async () => {
  render(
    <MemoryRouter initialEntries={["/runs/signal-run:test?tab=sensitivity"]}>
      <Routes>
        <Route path="/runs/:runId" element={<RunDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

  await waitFor(() => expect(screen.getByText("Run Snapshot")).toBeInTheDocument());
  expect(screen.getByRole("tab", { name: "Sensitivity" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("Threshold vs Consecutive Days")).toBeInTheDocument();
  expect(screen.getAllByTestId("plotly-chart").length).toBeGreaterThanOrEqual(3);
});
