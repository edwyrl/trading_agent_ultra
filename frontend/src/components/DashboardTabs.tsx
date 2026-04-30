import type { DashboardTabDTO } from "../types/api";

export type DashboardTabKey = string;

interface DashboardTabsProps {
  tabs: DashboardTabDTO[];
  activeTab: DashboardTabKey;
  onChange: (tab: DashboardTabKey) => void;
}

export function normalizeDashboardTab(value: string | null | undefined, tabs: DashboardTabDTO[]): DashboardTabKey {
  if (tabs.length === 0) {
    return "overview";
  }
  return tabs.some((tab) => tab.tab_key === value) ? (value as DashboardTabKey) : tabs[0].tab_key;
}

export function DashboardTabs({ tabs, activeTab, onChange }: DashboardTabsProps) {
  return (
    <div className="dashboard-tabs-wrap">
      <div className="dashboard-tabs" role="tablist" aria-label="Signal dashboard sections">
      {tabs.map((tab) => (
        <button
          key={tab.tab_key}
          type="button"
          role="tab"
          aria-selected={activeTab === tab.tab_key}
          className={`dashboard-tab${activeTab === tab.tab_key ? " active" : ""}`}
          onClick={() => onChange(tab.tab_key)}
        >
          {tab.label}
        </button>
      ))}
      </div>
    </div>
  );
}
