export type SignalRunStatus = "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELED";

export interface SignalDateRangeDTO {
  start_date: string;
  end_date: string;
}

export interface SignalRunRequestDTO {
  signal_key: string;
  date_range: SignalDateRangeDTO;
  config: Record<string, unknown>;
  source_type: "POSTGRES";
  max_retries: number;
  metadata: Record<string, unknown>;
}

export interface SignalRunStatusDTO {
  run_id: string;
  signal_key: string;
  source_type: string;
  status: SignalRunStatus;
  requested_start_date: string;
  requested_end_date: string;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  config: Record<string, unknown>;
  summary: Record<string, unknown>;
  error?: string | null;
}

export interface SignalArtifactDTO {
  artifact_type: string;
  artifact_key: string;
  uri: string;
  content_type: string;
  size_bytes: number;
  payload: Record<string, unknown>;
}

export interface DashboardOverviewDTO {
  signal_key: string;
  source_type: string;
  status: SignalRunStatus;
  requested_start_date: string;
  requested_end_date: string;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface DashboardMetricCardDTO {
  metric_key: string;
  label: string;
  value: number;
  unit: string;
  display: string;
}

export interface DashboardSeriesPointDTO {
  date: string;
  value: number;
}

export interface DashboardNamedSeriesDTO {
  label: string;
  metric_name?: string;
  points: DashboardSeriesPointDTO[];
}

export interface DashboardSectionDTO {
  section_key: string;
  title: string;
  section_type:
    | "timeseries"
    | "histogram"
    | "bar"
    | "scatter"
    | "boxplot"
    | "violin"
    | "heatmap"
    | "stat_cards"
    | "table"
    | "markdown"
    | "text";
  eyebrow: string;
  payload: Record<string, unknown>;
}

export interface DashboardTabDTO {
  tab_key: string;
  label: string;
  sections: DashboardSectionDTO[];
}

export interface DashboardPayloadDTO {
  run: SignalRunStatusDTO;
  overview: DashboardOverviewDTO;
  config_summary: {
    signal_key: string;
    source_type: string;
    date_range: {
      start_date: string;
      end_date: string;
    };
    config: Record<string, unknown>;
  };
  key_metrics: DashboardMetricCardDTO[];
  tabs: DashboardTabDTO[];
  artifacts: SignalArtifactDTO[];
}

export interface SignalPluginConfigSchemaFieldDTO {
  type: "integer" | "number" | "boolean" | "array" | "string" | "json";
  default?: unknown;
  minimum?: number;
  maximum?: number;
  items_type?: "integer" | "number";
  widget?: "code" | "json" | "textarea";
}

export interface SignalPluginMetaDTO {
  signal_key: string;
  name: string;
  description: string;
  version: string;
  config_schema: Record<string, SignalPluginConfigSchemaFieldDTO>;
  default_config: Record<string, unknown>;
  evaluation_modes: string[];
}
