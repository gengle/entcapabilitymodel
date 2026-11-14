import { useEffect, useId, useState } from "react";
import type { Resolved } from "./ui";

/** One editable value rendered with the control chosen for it in ui.yaml.
 *  value: what this file sets (null = nothing set here); emptyLabel describes what applies then ("inherit: 180"). */
export function Field(props: {
  ui: Resolved;
  value: string | null;
  emptyLabel: string;
  onCommit: (v: string | null) => void;
  clearable?: boolean;
  suggestions?: string[];
  label?: string;
  fallback?: string | null; // the value that applies when nothing is set here
}) {
  const { ui, value, emptyLabel, onCommit, clearable = true, suggestions = [], label } = props;
  const [v, setV] = useState(value ?? "");
  useEffect(() => setV(value ?? ""), [value]);
  const listId = useId();
  const name = useId();

  const commit = (x: string) => {
    const t = x.trim();
    const next = t === "" ? (clearable ? null : value) : t;
    if (next !== value) onCommit(next);
    else setV(value ?? "");
  };
  const keys = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") commit(v);
    if (e.key === "Escape") setV(value ?? "");
  };
  const clear =
    clearable && value !== null ? (
      <button type="button" className="clear" title="Remove the value set here" onClick={() => onCommit(null)}>
        ×
      </button>
    ) : null;
  const placeholder = emptyLabel;
  // a value outside the allowed list still shows, flagged, instead of silently disappearing
  const opts = value !== null && !ui.options.includes(value) ? [...ui.options, value] : ui.options;
  const off = (o: string) => (ui.options.includes(o) ? o : `${o} (not in list)`);

  switch (ui.control) {
    case "select":
      return (
        <span className="ctl">
          <select aria-label={label} value={v} onChange={(e) => commit(e.target.value)}>
            <option value="" disabled={!clearable && value !== null}>
              — {emptyLabel} —
            </option>
            {opts.map((o) => (
              <option key={o} value={o}>
                {off(o)}
              </option>
            ))}
          </select>
        </span>
      );
    case "radio":
      return (
        <span className="ctl radios" role="radiogroup" aria-label={label}>
          {opts.map((o) => (
            <label key={o} className={v === o ? "on" : ""}>
              <input type="radio" name={name} checked={v === o} onChange={() => commit(o)} />
              {off(o)}
            </label>
          ))}
          {clearable && (
            <label className={`none${v === "" ? " on" : ""}`}>
              <input type="radio" name={name} checked={v === ""} onChange={() => commit("")} />
              {emptyLabel}
            </label>
          )}
        </span>
      );
    case "slider": {
      const shown = v || (props.fallback && !isNaN(Number(props.fallback)) ? props.fallback : String(ui.min));
      return (
        <span className="ctl slider">
          <input
            type="range"
            aria-label={label}
            min={ui.min}
            max={ui.max}
            step={ui.step}
            value={shown}
            onChange={(e) => {
              setV(e.target.value);
              onCommit(e.target.value);
            }}
          />
          <output className={v ? "" : "muted"}>{v || `${shown} (${emptyLabel.split(":")[0]})`}</output>
          {clear}
        </span>
      );
    }
    case "textarea":
      return (
        <span className="ctl">
          <textarea aria-label={label} rows={3} value={v} placeholder={placeholder} onChange={(e) => setV(e.target.value)} onBlur={() => commit(v)} />
          {clear}
        </span>
      );
    case "number":
      return (
        <span className="ctl">
          <input
            type="number"
            aria-label={label}
            value={v}
            placeholder={placeholder}
            onChange={(e) => setV(e.target.value)}
            onBlur={() => commit(v)}
            onKeyDown={keys}
          />
          {clear}
        </span>
      );
    default: {
      const combo = ui.control === "combo" ? [...new Set([...ui.options, ...suggestions])] : [];
      return (
        <span className="ctl">
          <input
            aria-label={label}
            list={combo.length ? listId : undefined}
            value={v}
            placeholder={placeholder}
            onChange={(e) => setV(e.target.value)}
            onBlur={() => commit(v)}
            onKeyDown={keys}
          />
          {!!combo.length && (
            <datalist id={listId}>
              {combo.map((o) => (
                <option key={o} value={o} />
              ))}
            </datalist>
          )}
          {clear}
        </span>
      );
    }
  }
}
