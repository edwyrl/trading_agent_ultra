import React from "react";
import { MemoryRouter } from "react-router-dom";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { RunsPage } from "./RunsPage";
import { cancelRun, createRun, deleteRun, listRuns } from "../lib/api";

vi.mock("../lib/api", () => ({
  createRun: vi.fn(async () => ({
    run_id: "signal-run:new",
    signal_key: "market_breadth_crowding",
    source_type: "POSTGRES",
    status: "PENDING",
    requested_start_date: "2026-04-01",
    requested_end_date: "2026-04-20",
    created_at: "2026-04-20T00:00:00Z",
    updated_at: "2026-04-20T00:00:00Z",
    config: {},
    summary: {},
  })),
  listRuns: vi.fn(async () => [
    {
      run_id: "signal-run:test",
      signal_key: "liquidity_concentration",
      source_type: "POSTGRES",
      status: "SUCCEEDED",
      requested_start_date: "2026-04-01",
      requested_end_date: "2026-04-20",
      created_at: "2026-04-20T00:00:00Z",
      updated_at: "2026-04-20T00:00:00Z",
      config: {},
      summary: { event_count: 4, signal_day_count: 8, headline_metric_display: "82%" },
    },
  ]),
  cancelRun: vi.fn(async () => ({
    run_id: "signal-run:running",
    signal_key: "market_breadth_crowding",
    source_type: "POSTGRES",
    status: "CANCELED",
    requested_start_date: "2026-04-01",
    requested_end_date: "2026-04-20",
    created_at: "2026-04-20T00:00:00Z",
    updated_at: "2026-04-20T00:05:00Z",
    config: {},
    summary: {},
  })),
  deleteRun: vi.fn(async () => undefined),
  listPlugins: vi.fn(async () => [
    {
      signal_key: "liquidity_concentration",
      name: "Liquidity Concentration",
      description: "desc",
      version: "v2",
      config_schema: {
        top_pct: { type: "number", default: 0.05, minimum: 0.001, maximum: 0.5 },
        threshold: { type: "number", default: 0.45, minimum: 0.01, maximum: 1 },
        use_money: { type: "boolean", default: true },
      },
      default_config: { top_pct: 0.05, threshold: 0.45, use_money: true },
      evaluation_modes: ["EVENT_STUDY"],
    },
    {
      signal_key: "market_breadth_crowding",
      name: "Market Breadth Crowding",
      description: "breadth desc",
      version: "v1",
      config_schema: {
        threshold: { type: "number", default: 0.7, minimum: 0, maximum: 1 },
        consecutive_days: { type: "integer", default: 2, minimum: 1 },
        sens_thresholds: { type: "array", items_type: "number", default: [0.55, 0.6, 0.7] },
      },
      default_config: { threshold: 0.7, consecutive_days: 2, sens_thresholds: [0.55, 0.6, 0.7] },
      evaluation_modes: ["EVENT_STUDY"],
    },
    {
      signal_key: "custom_python_signal",
      name: "Custom Python Signal",
      description: "custom desc",
      version: "v1",
      config_schema: {
        script: { type: "string", widget: "code", default: "def compute_signal(ctx):\n    return {\"metrics\": []}\n" },
        params: { type: "json", widget: "json", default: { threshold: 0.8 } },
      },
      default_config: {
        script: "def compute_signal(ctx):\n    return {\"metrics\": []}\n",
        params: { threshold: 0.8 },
      },
      evaluation_modes: ["EVENT_STUDY"],
    },
  ]),
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

function renderRunsPage() {
  return render(
    <MemoryRouter>
      <RunsPage />
    </MemoryRouter>,
  );
}

test("runs page renders fetched runs", async () => {
  renderRunsPage();

  await waitFor(() => expect(screen.getByText("Liquidity Concentration")).toBeInTheDocument());
  expect(screen.getByLabelText("Run status summary")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "All Runs" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("Open detail")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Delete run signal-run:test/i })).toBeInTheDocument();
});

test("opens schema-driven new run panel and switches plugins", async () => {
  const user = userEvent.setup();
  renderRunsPage();

  await user.click(screen.getByRole("button", { name: "New Run" }));

  expect(screen.getByRole("region", { name: "New signal run" })).toBeInTheDocument();
  expect(screen.getByLabelText("Plugin")).toHaveValue("liquidity_concentration");
  expect(screen.getByLabelText("Top Pct")).toHaveValue(0.05);
  expect(screen.getByLabelText("Use Money")).toBeChecked();

  await user.selectOptions(screen.getByLabelText("Plugin"), "market_breadth_crowding");

  expect(screen.getByRole("heading", { name: "Market Breadth Crowding" })).toBeInTheDocument();
  expect(screen.getByLabelText("Threshold")).toHaveValue(0.7);
  expect(screen.getByLabelText("Consecutive Days")).toHaveValue(2);
});

test("submits a valid breadth run and refreshes list", async () => {
  const user = userEvent.setup();
  renderRunsPage();

  await user.click(screen.getByRole("button", { name: "New Run" }));
  await user.selectOptions(screen.getByLabelText("Plugin"), "market_breadth_crowding");
  await user.clear(screen.getByLabelText("Threshold"));
  await user.type(screen.getByLabelText("Threshold"), "0.65");
  await user.click(screen.getByRole("button", { name: "Submit run" }));

  await waitFor(() => expect(createRun).toHaveBeenCalledTimes(1));
  expect(createRun).toHaveBeenCalledWith({
    signal_key: "market_breadth_crowding",
    date_range: {
      start_date: "2026-04-01",
      end_date: "2026-04-20",
    },
    source_type: "POSTGRES",
    max_retries: 3,
    metadata: {
      submitted_from: "frontend",
    },
    config: {
      threshold: 0.65,
      consecutive_days: 2,
      sens_thresholds: [0.55, 0.6, 0.7],
    },
  });
  await waitFor(() => expect(listRuns).toHaveBeenCalledTimes(2));
  expect(screen.getByText(/Queued signal-run:new/)).toBeInTheDocument();
});

test("submits a custom python signal run", async () => {
  const user = userEvent.setup();
  renderRunsPage();

  await user.click(screen.getByRole("button", { name: "New Run" }));
  await user.selectOptions(screen.getByLabelText("Plugin"), "custom_python_signal");
  fireEvent.change(screen.getByLabelText("Params"), { target: { value: "{\"threshold\":0.75}" } });
  await user.click(screen.getByRole("button", { name: "Submit run" }));

  await waitFor(() => expect(createRun).toHaveBeenCalledTimes(1));
  expect(createRun).toHaveBeenCalledWith({
    signal_key: "custom_python_signal",
    date_range: {
      start_date: "2026-04-01",
      end_date: "2026-04-20",
    },
    source_type: "POSTGRES",
    max_retries: 3,
    metadata: {
      submitted_from: "frontend",
    },
    config: {
      script: "def compute_signal(ctx):\n    return {\"metrics\": []}\n",
      params: { threshold: 0.75 },
    },
  });
});

test("blocks invalid date range before submit", async () => {
  const user = userEvent.setup();
  renderRunsPage();

  await user.click(screen.getByRole("button", { name: "New Run" }));
  await user.clear(screen.getByLabelText("Start date"));
  await user.type(screen.getByLabelText("Start date"), "2026-04-21");
  await user.click(screen.getByRole("button", { name: "Submit run" }));

  expect(screen.getByText("Start date must be before or equal to end date.")).toBeInTheDocument();
  expect(createRun).not.toHaveBeenCalled();
});

test("keeps form values when submit fails", async () => {
  vi.mocked(createRun).mockRejectedValueOnce(new Error("Request failed: 500"));
  const user = userEvent.setup();
  renderRunsPage();

  await user.click(screen.getByRole("button", { name: "New Run" }));
  await user.selectOptions(screen.getByLabelText("Plugin"), "market_breadth_crowding");
  await user.clear(screen.getByLabelText("Threshold"));
  await user.type(screen.getByLabelText("Threshold"), "0.62");
  await user.click(screen.getByRole("button", { name: "Submit run" }));

  await waitFor(() => expect(screen.getByText("Request failed: 500")).toBeInTheDocument());
  expect(screen.getByLabelText("Threshold")).toHaveValue(0.62);
});

test("stops an active run from task center", async () => {
  vi.mocked(listRuns).mockResolvedValueOnce([
    {
      run_id: "signal-run:running",
      signal_key: "market_breadth_crowding",
      source_type: "POSTGRES",
      status: "RUNNING",
      requested_start_date: "2026-04-01",
      requested_end_date: "2026-04-20",
      created_at: "2026-04-20T00:00:00Z",
      updated_at: "2026-04-20T00:02:00Z",
      config: {},
      summary: { event_count: 0, signal_day_count: 0 },
    },
  ]);
  vi.mocked(listRuns).mockResolvedValueOnce([]);
  const user = userEvent.setup();
  renderRunsPage();

  await waitFor(() => expect(screen.getByText("Market Breadth Crowding")).toBeInTheDocument());
  await user.click(screen.getByRole("button", { name: /Stop run signal-run:running/i }));

  await waitFor(() => expect(cancelRun).toHaveBeenCalledWith("signal-run:running"));
  await waitFor(() => expect(screen.getByText(/Canceled signal-run:running/)).toBeInTheDocument());
});

test("deletes a completed run from task center", async () => {
  const user = userEvent.setup();
  renderRunsPage();

  await waitFor(() => expect(screen.getByText("Liquidity Concentration")).toBeInTheDocument());
  await user.click(screen.getByRole("button", { name: /Delete run signal-run:test/i }));

  await waitFor(() => expect(deleteRun).toHaveBeenCalledWith("signal-run:test"));
  await waitFor(() => expect(screen.getByText(/Deleted signal-run:test/)).toBeInTheDocument());
});
