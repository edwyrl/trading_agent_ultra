import "@testing-library/jest-dom";
import React from "react";
import { vi } from "vitest";

vi.mock("react-plotly.js", () => ({
  default: ({ data, layout }: { data?: unknown[]; layout?: { title?: { text?: string } } }) =>
    React.createElement(
      "div",
      {
        "data-testid": "plotly-chart",
        role: "img",
        "aria-label": layout?.title?.text ?? "plotly chart",
      },
      `traces:${data?.length ?? 0}`,
    ),
}));

class ResizeObserverMock {
  observe() {}

  unobserve() {}

  disconnect() {}
}

Object.defineProperty(window, "ResizeObserver", {
  writable: true,
  value: ResizeObserverMock,
});
