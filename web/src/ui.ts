// Form-control mapping: which UI control edits each field. Stored in the model folder as ui.yaml
// (outside the model's includes, so it never affects validation). Keys per scope:
//   capability: <prop>     entity: <prop>     relation: <verb>.<attr>  (or just <attr> for every verb)
import { isMap, parse, parseDocument } from "yaml";
import type { PropDef } from "./types";

export const UI_FILE = "ui.yaml";

export type Control = "text" | "textarea" | "combo" | "number" | "slider" | "select" | "radio";
export type Scope = "capability" | "entity" | "relation";

export interface FieldUi {
  control?: Control;
  options?: string[];
  min?: number;
  max?: number;
  step?: number;
}

export type UiConfig = Record<Scope, Record<string, FieldUi>>;

export interface Resolved {
  control: Control;
  base: Control; // the default for the field's type
  options: string[];
  min: number;
  max: number;
  step: number;
}

export const CONTROL_LABEL: Record<Control, string> = {
  text: "Text box",
  textarea: "Multi-line text",
  combo: "Text with suggestions",
  number: "Number box",
  slider: "Slider",
  select: "Drop-down",
  radio: "Radio buttons",
};

/** Controls that make sense for a field, by its schema type. */
export function controlsFor(def: PropDef): Control[] {
  if (def.enum) return ["select", "radio"];
  if (def.type === "int") return ["number", "slider", "select", "radio"];
  return ["text", "textarea", "combo", "select", "radio"];
}

export const needsOptions = (c: Control) => c === "select" || c === "radio";

export const HEADER = `# Form controls used by the viewer's edit forms. The Forms page writes this file; you can also edit it here.
# It is not part of the model (nothing includes it), so it never changes validation.
#   capability: <prop>   entity: <prop>   relation: <verb>.<attr>
#   control: text | textarea | combo | number | slider | select | radio
#   Defaults: enum -> select, int -> number, string -> text.
#   select / radio / combo on a non-enum field take options: [...]; slider takes min, max and step.
`;

export function parseUi(text: string | null): UiConfig {
  const cfg: UiConfig = { capability: {}, entity: {}, relation: {} };
  let raw: unknown;
  try {
    raw = text ? parse(text) : null;
  } catch {
    return cfg;
  }
  if (!raw || typeof raw !== "object") return cfg;
  for (const scope of Object.keys(cfg) as Scope[]) {
    const m = (raw as Record<string, unknown>)[scope];
    if (!m || typeof m !== "object") continue;
    for (const [k, v] of Object.entries(m as Record<string, unknown>)) {
      if (typeof v === "string") cfg[scope][k] = { control: v as Control };
      else if (v && typeof v === "object") {
        const o = v as Record<string, unknown>;
        const num = (x: unknown) => (x === undefined || x === null || x === "" || isNaN(Number(x)) ? undefined : Number(x));
        cfg[scope][k] = {
          control: typeof o.control === "string" ? (o.control as Control) : undefined,
          options: Array.isArray(o.options) ? o.options.map(String) : undefined,
          min: num(o.min),
          max: num(o.max),
          step: num(o.step),
        };
      }
    }
  }
  return cfg;
}

export function lookup(cfg: UiConfig, scope: Scope, key: string): FieldUi {
  return cfg[scope][key] ?? (scope === "relation" ? cfg.relation[key.split(".").pop()!] : undefined) ?? {};
}

export function resolveUi(cfg: UiConfig, scope: Scope, key: string, def: PropDef): Resolved {
  const u = lookup(cfg, scope, key);
  const base: Control = def.enum ? "select" : def.type === "int" ? "number" : "text";
  let control = u.control && controlsFor(def).includes(u.control) ? u.control : base;
  const options = def.enum ?? u.options ?? [];
  if (needsOptions(control) && !options.length) control = base;
  const min = u.min ?? 0;
  const max = u.max ?? Math.max(min + 1, 100);
  return { control, base, options, min, max, step: u.step ?? 1 };
}

/** ui.yaml text with one field's setting replaced (null removes it). Keeps comments and other entries. */
export function setFieldUi(text: string | null, scope: Scope, key: string, u: FieldUi | null, def: PropDef): string {
  const doc = parseDocument(text?.trim() ? text : HEADER + "{}\n");
  if (doc.errors.length) throw new Error(`${UI_FILE} has a YAML error: ${doc.errors[0].message}`);
  if (!isMap(doc.contents)) doc.contents = doc.createNode({}) as unknown as typeof doc.contents;
  const root = doc.contents as unknown as import("yaml").YAMLMap;
  root.flow = false;
  if (u === null) {
    doc.deleteIn([scope, key]);
    const m = doc.getIn([scope]);
    if (isMap(m) && !m.items.length) doc.deleteIn([scope]);
  } else {
    const out: Record<string, unknown> = { control: u.control };
    if (u.options?.length) out.options = u.options.map((o) => (def.type === "int" && /^-?\d+$/.test(o) ? Number(o) : o));
    if (u.control === "slider") Object.assign(out, { min: u.min ?? 0, max: u.max ?? 100, step: u.step ?? 1 });
    if (!isMap(doc.getIn([scope]))) doc.setIn([scope], doc.createNode({}));
    (doc.getIn([scope]) as import("yaml").YAMLMap).flow = false;
    doc.setIn([scope, key], doc.createNode(out, { flow: true }));
  }
  return doc.toString({ lineWidth: 0, flowCollectionPadding: false });
}
