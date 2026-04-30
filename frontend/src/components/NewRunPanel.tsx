import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Braces, Code2, FlaskConical, LineChart, Waves } from "lucide-react";
import type { SignalPluginConfigSchemaFieldDTO, SignalPluginMetaDTO, SignalRunRequestDTO } from "../types/api";

interface NewRunPanelProps {
  plugins: SignalPluginMetaDTO[];
  onCancel: () => void;
  onSubmit: (request: SignalRunRequestDTO) => Promise<void>;
}

interface NewRunFormState {
  signalKey: string;
  startDate: string;
  endDate: string;
  configValues: Record<string, string | boolean>;
}

type ParseFieldResult = { ok: true; value: unknown } | { ok: false; error: string };

function toInputValue(value: unknown): string | boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  if (typeof value === "object" && value !== null) {
    return JSON.stringify(value, null, 2);
  }
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
}

function titleize(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function buildInitialState(plugin: SignalPluginMetaDTO | undefined): NewRunFormState {
  const configValues: Record<string, string | boolean> = {};
  if (plugin) {
    for (const [field, schema] of Object.entries(plugin.config_schema)) {
      const defaultValue = plugin.default_config[field] ?? schema.default;
      configValues[field] = toInputValue(defaultValue);
    }
  }
  return {
    signalKey: plugin?.signal_key ?? "",
    startDate: "2026-04-01",
    endDate: "2026-04-20",
    configValues,
  };
}

export function NewRunPanel({ plugins, onCancel, onSubmit }: NewRunPanelProps) {
  const defaultPlugin = useMemo(
    () => plugins.find((plugin) => plugin.signal_key === "liquidity_concentration") ?? plugins[0],
    [plugins],
  );
  const [form, setForm] = useState<NewRunFormState>(() => buildInitialState(defaultPlugin));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!defaultPlugin) {
      return;
    }
    setForm((current) => {
      if (current.signalKey) {
        return current;
      }
      return buildInitialState(defaultPlugin);
    });
  }, [defaultPlugin]);

  const activePlugin = plugins.find((plugin) => plugin.signal_key === form.signalKey) ?? defaultPlugin;

  function updateField(field: string, value: string | boolean) {
    setForm((current) => ({
      ...current,
      configValues: {
        ...current.configValues,
        [field]: value,
      },
    }));
  }

  function updateSignal(signalKey: string) {
    const plugin = plugins.find((item) => item.signal_key === signalKey);
    setForm((current) => {
      const next = buildInitialState(plugin);
      return {
        ...next,
        startDate: current.startDate,
        endDate: current.endDate,
      };
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const validation = buildRequest(form, activePlugin);
    if (typeof validation === "string") {
      setError(validation);
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit(validation);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Unknown error");
    } finally {
      setSubmitting(false);
    }
  }

  if (!activePlugin) {
    return <div className="error-state compact">No signal plugins available.</div>;
  }
  const isCustomSignal = activePlugin.signal_key === "custom_python_signal";
  const codeFields = Object.entries(activePlugin.config_schema).filter(([, schema]) => schema.widget === "code");
  const secondaryFields = Object.entries(activePlugin.config_schema).filter(([, schema]) => schema.widget !== "code");

  return (
    <section className="panel new-run-panel" aria-label="New signal run">
      <div className="panel-header">
        <div>
          <p className="eyebrow">New Run</p>
          <h2>{activePlugin.name}</h2>
          <p className="page-copy">{activePlugin.description}</p>
        </div>
        <button type="button" onClick={onCancel} disabled={submitting}>
          Close
        </button>
      </div>

      {error ? <div className="error-state compact" role="alert">{error}</div> : null}

      <form className="new-run-form" onSubmit={handleSubmit}>
        <fieldset>
          <legend>Research Template</legend>
          <div className="template-grid">
            {plugins.map((plugin) => {
              const Icon = plugin.signal_key === "custom_python_signal" ? Code2 : plugin.signal_key === "market_breadth_crowding" ? Waves : LineChart;
              return (
                <button
                  type="button"
                  key={plugin.signal_key}
                  className={`template-card${form.signalKey === plugin.signal_key ? " active" : ""}`}
                  onClick={() => updateSignal(plugin.signal_key)}
                  aria-pressed={form.signalKey === plugin.signal_key}
                >
                  <Icon size={20} aria-hidden="true" />
                  <strong>{plugin.name}</strong>
                  <span>{plugin.description}</span>
                </button>
              );
            })}
          </div>
          <label className="visually-hidden">
            Plugin
            <select value={form.signalKey} onChange={(event) => updateSignal(event.target.value)}>
              {plugins.map((plugin) => (
                <option key={plugin.signal_key} value={plugin.signal_key}>
                  {plugin.name}
                </option>
              ))}
            </select>
          </label>
        </fieldset>

        <fieldset>
          <legend>Date Range</legend>
          <label>
            Start date
            <input type="date" value={form.startDate} onChange={(event) => setForm((current) => ({ ...current, startDate: event.target.value }))} />
          </label>
          <label>
            End date
            <input type="date" value={form.endDate} onChange={(event) => setForm((current) => ({ ...current, endDate: event.target.value }))} />
          </label>
        </fieldset>

        {isCustomSignal ? (
          <div className="custom-signal-layout">
            <fieldset className="code-fieldset">
              <legend>Custom Logic</legend>
              {codeFields.map(([field, schema]) => renderConfigField({ field, schema, value: form.configValues[field], updateField }))}
            </fieldset>
            <aside className="script-contract">
              <div className="contract-card">
                <FlaskConical size={18} aria-hidden="true" />
                <div>
                  <strong>Function contract</strong>
                  <p>Define <code>compute_signal(ctx)</code> and return metrics, events, stats, and summary.</p>
                </div>
              </div>
              <div className="contract-card">
                <Braces size={18} aria-hidden="true" />
                <div>
                  <strong>Available ctx</strong>
                  <p><code>trade_days</code>, <code>snapshots</code>, <code>params</code>, <code>start_date</code>, <code>end_date</code>.</p>
                </div>
              </div>
              <fieldset className="side-fieldset">
                <legend>Params & Output</legend>
                {secondaryFields.map(([field, schema]) => renderConfigField({ field, schema, value: form.configValues[field], updateField }))}
              </fieldset>
            </aside>
          </div>
        ) : (
          <fieldset>
            <legend>Parameters</legend>
            {Object.entries(activePlugin.config_schema).map(([field, schema]) =>
              renderConfigField({ field, schema, value: form.configValues[field], updateField }),
            )}
          </fieldset>
        )}

        <div className="form-actions">
          <button className="primary-action" type="submit" disabled={submitting}>
            {submitting ? "Submitting..." : "Submit run"}
          </button>
          <button type="button" onClick={onCancel} disabled={submitting}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  );
}

function renderConfigField({
  field,
  schema,
  value,
  updateField,
}: {
  field: string;
  schema: SignalPluginConfigSchemaFieldDTO;
  value: string | boolean | undefined;
  updateField: (field: string, value: string | boolean) => void;
}) {
  const fieldId = `signal-config-${field}`;
  const helper = buildHelperText(field, schema);
  if (schema.type === "boolean") {
    return (
      <label key={field} className="toggle-row" htmlFor={fieldId}>
        <input
          id={fieldId}
          type="checkbox"
          checked={Boolean(value)}
          onChange={(event) => updateField(field, event.target.checked)}
        />
        <span>{titleize(field)}</span>
      </label>
    );
  }
  if (schema.type === "string" || schema.type === "json") {
    return (
      <label key={field} htmlFor={fieldId} className="wide-field field-stack">
        <span>{titleize(field)}</span>
        <textarea
          id={fieldId}
          aria-label={titleize(field)}
          className={schema.widget === "code" ? "code-input" : schema.widget === "json" ? "json-input" : undefined}
          value={typeof value === "boolean" ? "" : value}
          onChange={(event) => updateField(field, event.target.value)}
          aria-describedby={helper ? `${fieldId}-helper` : undefined}
        />
        {helper ? <small id={`${fieldId}-helper`}>{helper}</small> : null}
      </label>
    );
  }
  return (
    <label key={field} htmlFor={fieldId} className="field-stack">
      <span>{titleize(field)}</span>
      <input
        id={fieldId}
        aria-label={titleize(field)}
        type={schema.type === "integer" || schema.type === "number" ? "number" : "text"}
        min={schema.minimum}
        max={schema.maximum}
        step={schema.type === "integer" ? 1 : "any"}
        value={typeof value === "boolean" ? "" : value}
        onChange={(event) => updateField(field, event.target.value)}
        aria-describedby={helper ? `${fieldId}-helper` : undefined}
      />
      {helper ? <small id={`${fieldId}-helper`}>{helper}</small> : null}
    </label>
  );
}

function buildHelperText(field: string, schema: SignalPluginConfigSchemaFieldDTO) {
  if (schema.widget === "code") {
    return "Python function body. Imports, file access, and dunder attributes are blocked by the backend guard.";
  }
  if (schema.widget === "json") {
    return "JSON object passed to ctx.params.";
  }
  if (schema.type === "array") {
    return "Comma-separated numeric values.";
  }
  const bounds = [schema.minimum !== undefined ? `min ${schema.minimum}` : "", schema.maximum !== undefined ? `max ${schema.maximum}` : ""]
    .filter(Boolean)
    .join(", ");
  return bounds || (field === "artifact_dir" ? "Relative artifact output path." : "");
}

function buildRequest(form: NewRunFormState, plugin: SignalPluginMetaDTO | undefined): SignalRunRequestDTO | string {
  if (!plugin) {
    return "Signal plugin is required.";
  }
  if (!form.startDate || !form.endDate) {
    return "Start date and end date are required.";
  }
  if (form.startDate > form.endDate) {
    return "Start date must be before or equal to end date.";
  }

  const config: Record<string, unknown> = {};
  for (const [field, schema] of Object.entries(plugin.config_schema)) {
    const rawValue = form.configValues[field];
    const parsed = parseFieldValue(field, schema, rawValue);
    if (!parsed.ok) {
      return parsed.error;
    }
    config[field] = parsed.value;
  }

  return {
    signal_key: plugin.signal_key,
    date_range: {
      start_date: form.startDate,
      end_date: form.endDate,
    },
    source_type: "POSTGRES",
    max_retries: 3,
    metadata: {
      submitted_from: "frontend",
    },
    config,
  };
}

function parseFieldValue(field: string, schema: SignalPluginConfigSchemaFieldDTO, rawValue: string | boolean | undefined): ParseFieldResult {
  if (schema.type === "boolean") {
    return { ok: true, value: Boolean(rawValue) };
  }

  const rawTextValue = String(rawValue ?? "");
  const textValue = rawTextValue.trim();
  if (schema.type === "integer") {
    const parsed = Number(textValue);
    if (!Number.isInteger(parsed)) {
      return { ok: false, error: `${titleize(field)} must be a valid integer.` };
    }
    if (schema.minimum !== undefined && parsed < schema.minimum) {
      return { ok: false, error: `${titleize(field)} must be at least ${schema.minimum}.` };
    }
    if (schema.maximum !== undefined && parsed > schema.maximum) {
      return { ok: false, error: `${titleize(field)} must be at most ${schema.maximum}.` };
    }
    return { ok: true, value: parsed };
  }

  if (schema.type === "number") {
    const parsed = Number(textValue);
    if (!Number.isFinite(parsed)) {
      return { ok: false, error: `${titleize(field)} must be a valid number.` };
    }
    if (schema.minimum !== undefined && parsed < schema.minimum) {
      return { ok: false, error: `${titleize(field)} must be at least ${schema.minimum}.` };
    }
    if (schema.maximum !== undefined && parsed > schema.maximum) {
      return { ok: false, error: `${titleize(field)} must be at most ${schema.maximum}.` };
    }
    return { ok: true, value: parsed };
  }

  if (schema.type === "array") {
    const tokens = textValue
      .split(",")
      .map((token) => token.trim())
      .filter(Boolean);
    if (tokens.length === 0) {
      return { ok: false, error: `${titleize(field)} must include at least one value.` };
    }
    const parsed = tokens.map((token) => Number(token));
    if (parsed.some((value) => !Number.isFinite(value))) {
      return { ok: false, error: `${titleize(field)} must be a comma-separated list of numbers.` };
    }
    if (schema.items_type === "integer") {
      if (parsed.some((value) => !Number.isInteger(value))) {
        return { ok: false, error: `${titleize(field)} must contain integers only.` };
      }
      return { ok: true, value: parsed.map((value) => Math.trunc(value)) };
    }
    return { ok: true, value: parsed };
  }

  if (schema.type === "json") {
    try {
      const parsed = JSON.parse(textValue);
      if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
        return { ok: false, error: `${titleize(field)} must be a JSON object.` };
      }
      return { ok: true, value: parsed as Record<string, unknown> };
    } catch {
      return { ok: false, error: `${titleize(field)} must be valid JSON.` };
    }
  }

  return { ok: true, value: rawTextValue };
}
