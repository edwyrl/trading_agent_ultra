import type { DashboardNamedSeriesDTO } from "../../types/api";

export function mergeSeriesByDate(seriesCollection: DashboardNamedSeriesDTO[]): Array<Record<string, string | number>> {
  const merged = new Map<string, Record<string, string | number>>();
  for (const series of seriesCollection) {
    const key = series.metric_name ?? series.label;
    for (const point of series.points) {
      const row = merged.get(point.date) ?? { date: point.date };
      row[key] = point.value;
      merged.set(point.date, row);
    }
  }
  return Array.from(merged.values()).sort((left, right) => String(left.date).localeCompare(String(right.date)));
}
