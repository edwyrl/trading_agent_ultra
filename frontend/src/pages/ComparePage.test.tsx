import React from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { ComparePage } from "./ComparePage";

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>;
}

test("compare route redirects to sensitivity tab", () => {
  render(
    <MemoryRouter initialEntries={["/runs/signal-run:test/compare"]}>
      <Routes>
        <Route path="/runs/:runId/compare" element={<ComparePage />} />
        <Route path="/runs/:runId" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );

  expect(screen.getByTestId("location")).toHaveTextContent("/runs/signal-run:test?tab=sensitivity");
});
