import { useState } from "react";
import { Field } from "./Field";
import { fileHref, groupBy, href, label, useModel, uuid } from "./model";
import type { Cap, Ent, PropDef, PropVal, RelationType, Snapshot } from "./types";
import { CONTROL_LABEL, controlsFor, lookup, needsOptions, resolveUi, setFieldUi, type Control, type FieldUi, type Scope, type UiConfig } from "./ui";
import {
  addChildCap,
  addRel,
  capOrThrow,
  removeChildCap,
  removeRel,
  root,
  setProp,
  setRelAttr,
  setRelTarget,
  setScalar,
  typed,
} from "./yamledit";

// ---------------------------------------------------------------- shared
function emptyLabel(p: PropVal | undefined, def: PropDef): string {
  if (p && p.origin.startsWith("inherited from ")) return `inherit: ${p.value}`;
  if (p && p.origin === "root default") return `default: ${p.value}`;
  if (def.default != null) return `default: ${def.default}`;
  return def.required ? "required" : "not set";
}

/** Distinct values a field already has somewhere in the model (suggestions for combo boxes). */
function seen(snap: Snapshot, scope: "capability" | "entity", name: string): string[] {
  const out = new Set<string>();
  if (scope === "entity") snap.entities.forEach((e) => e.props.forEach((p) => p.name === name && p.value && out.add(p.value)));
  else {
    const walk = (c: Cap) => {
      c.props.forEach((p) => p.name === name && p.origin === "local" && p.value && out.add(p.value));
      c.children.forEach(walk);
    };
    snap.capabilities.forEach(walk);
  }
  return [...out].sort();
}

function Via({ src }: { src: string }) {
  return (
    <a className="via" href={fileHref(src)} title="This value comes from a fragment; a value set here overrides it">
      from {src.split("/").pop()}
    </a>
  );
}

function NameField({ value, onCommit, title }: { value: string; onCommit: (v: string) => void; title: string }) {
  const [v, setV] = useState(value);
  const [last, setLast] = useState(value);
  if (last !== value) {
    setLast(value);
    setV(value);
  }
  const commit = () => (v.trim() && v.trim() !== value ? onCommit(v.trim()) : setV(value));
  return (
    <input
      className="name-input"
      aria-label={title}
      title={title}
      value={v}
      onChange={(e) => setV(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") setV(value);
      }}
    />
  );
}

function FormBar({ path }: { path: string }) {
  const { dirty, save } = useModel();
  return (
    <div className="form-bar">
      <span className="muted small">
        Edits go to <span className="mono">{path}</span> and preview immediately. Press Save to write the file.{" "}
        <a href="#/forms">Choose controls…</a>
      </span>
      <span className="grow" />
      <button className="primary" disabled={!dirty.has(path)} onClick={save} title="Ctrl+S">
        Save
      </button>
    </div>
  );
}

// ---------------------------------------------------------------- entity
function entityDefs(snap: Snapshot, ent: Ent): Map<string, PropDef> {
  const types = new Map(snap.schema.entityTypes.map((t) => [t.name, t]));
  const out = new Map<string, PropDef>();
  for (const t of ent.chain) for (const p of types.get(t)?.props ?? []) if (!out.has(p.name)) out.set(p.name, p);
  return out;
}

const conforms = (chain: string[], names: string[]) => names.includes("*") || chain.some((t) => names.includes(t));

/** Targets a relation type allows, as [id, label] pairs (capabilities by path, entities by name). */
function targetOptions(snap: Snapshot, rt: RelationType, self: string): { caps: Cap[]; ents: Ent[] } {
  const caps: Cap[] = [];
  if (rt.to.includes(snap.schema.root) || rt.to.includes("*")) {
    const walk = (c: Cap) => {
      if (!rt.minLevel || c.level >= rt.minLevel) caps.push(c);
      c.children.forEach(walk);
    };
    snap.capabilities.forEach(walk);
  }
  const ents = snap.entities.filter((e) => e.id !== self && conforms(e.chain, rt.to));
  return { caps, ents };
}

/** What to write for a target: an entity's name, a capability's name when unique, else its path. */
function targetText(snap: Snapshot, id: string): string {
  if (id.startsWith("ent:")) return id.slice(4);
  const name = label(id).toLowerCase();
  let hits = 0;
  const walk = (c: Cap) => {
    if (c.name.toLowerCase() === name) hits++;
    c.children.forEach(walk);
  };
  snap.capabilities.forEach(walk);
  return hits === 1 ? label(id) : id.slice(4);
}

function TargetSelect({ rt, value, self, onPick, placeholder }: { rt: RelationType; value: string | null; self: string; onPick: (id: string) => void; placeholder?: string }) {
  const { snap } = useModel();
  const { caps, ents } = targetOptions(snap, rt, self);
  const known = value && (caps.some((c) => c.id === value) || ents.some((e) => e.id === value));
  return (
    <select className="target" aria-label={`${rt.name} target`} value={value ?? ""} onChange={(e) => e.target.value && onPick(e.target.value)}>
      <option value="">{placeholder ?? "— choose —"}</option>
      {value && !known && <option value={value}>{value.startsWith("?:") ? value.slice(2) : label(value)} (not allowed here)</option>}
      {!!caps.length && (
        <optgroup label={`Capabilities${rt.minLevel ? ` (L${rt.minLevel}+)` : ""}`}>
          {caps.map((c) => (
            <option key={c.id} value={c.id}>
              {"  ".repeat(Math.max(0, c.level - (rt.minLevel ?? 1)))}
              {c.name}
              {c.level <= 2 ? "" : ` · ${c.path.split("/").slice(0, -1).pop()}`}
            </option>
          ))}
        </optgroup>
      )}
      {!!ents.length && (
        <optgroup label={`Entities (${rt.to.join(", ")})`}>
          {ents.map((e) => (
            <option key={e.id} value={e.id}>
              {e.name} · {e.type}
            </option>
          ))}
        </optgroup>
      )}
    </select>
  );
}

export function EntityForm({ ent }: { ent: Ent }) {
  const { snap, ui, mutate } = useModel();
  const path = ent.src;
  const defs = entityDefs(snap, ent);
  const rtypes = new Map(snap.schema.relationTypes.map((r) => [r.name, r]));
  const verbs = snap.schema.relationTypes.filter((r) => conforms(ent.chain, r.from));
  const [newVerb, setNewVerb] = useState("");
  const verb = newVerb || verbs[0]?.name || "";

  // own index of each relation within its verb list in this file (fragment entries are read-only here)
  const counters = new Map<string, number>();
  const rels = ent.relations.map((r) => {
    const own = r.src === path;
    const i = own ? (counters.get(r.verb) ?? 0) : -1;
    if (own) counters.set(r.verb, i + 1);
    return { r, own, i };
  });

  return (
    <div className="form">
      <FormBar path={path} />
      <table className="form-grid">
        <tbody>
          <tr>
            <th>name</th>
            <td>
              <NameField
                value={ent.name}
                title="Entity name (references to the old name are not renamed)"
                onCommit={(v) => mutate(path, (d) => setScalar(d, root(d), "name", v)) && (location.hash = href("ent:" + v))}
              />
            </td>
          </tr>
          <tr>
            <th>type</th>
            <td>
              <span className="ctl">
                <select aria-label="Entity type" value={ent.type} onChange={(e) => mutate(path, (d) => setScalar(d, root(d), "type", e.target.value))}>
                  {!snap.schema.entityTypes.some((t) => t.name === ent.type) && <option value={ent.type}>{ent.type} (unknown)</option>}
                  {snap.schema.entityTypes.map((t) => (
                    <option key={t.name} value={t.name}>
                      {t.name}
                      {t.parent ? ` (is-a ${t.parent})` : ""}
                    </option>
                  ))}
                </select>
              </span>
            </td>
          </tr>
        </tbody>
      </table>

      <h4>Properties</h4>
      <table className="form-grid">
        <tbody>
          {ent.props.map((p) => {
            const def = defs.get(p.name);
            const local = p.origin === "local" || p.origin === "unknown";
            const fromFragment = local && !!p.src && p.src !== path;
            if (!def)
              return (
                <tr key={p.name}>
                  <th className="bad">{p.name}</th>
                  <td>
                    <span className="err-text">not a property of {ent.type}</span>{" "}
                    {!fromFragment && (
                      <button className="link-btn" onClick={() => mutate(path, (d) => setProp(d, root(d), p.name, null))}>
                        remove
                      </button>
                    )}
                  </td>
                </tr>
              );
            return (
              <tr key={p.name}>
                <th title={def.spec}>
                  {p.name}
                  {def.required && <span className="req">*</span>}
                </th>
                <td>
                  <Field
                    label={p.name}
                    ui={resolveUi(ui, "entity", p.name, def)}
                    value={local ? p.value : null}
                    fallback={def.default}
                    emptyLabel={emptyLabel(undefined, def)}
                    clearable={!fromFragment}
                    suggestions={seen(snap, "entity", p.name)}
                    onCommit={(v) => mutate(path, (d) => setProp(d, root(d), p.name, v === null ? null : typed(def.type, v)))}
                  />
                  {fromFragment && <Via src={p.src!} />}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <h4>Relations</h4>
      {groupBy(rels, (x) => x.r.verb).map(([v, xs]) => {
        const rt = rtypes.get(v);
        return (
          <div key={v} className="rel-edit">
            <div className="rel-verb mono">
              {v}
              {rt?.inverse && <span className="muted"> (inverse {rt.inverse})</span>}
            </div>
            {xs.map(({ r, own, i }, n) => (
              <div key={n} className={`rel-row${r.err ? " bad" : ""}`}>
                {own && rt ? (
                  <TargetSelect rt={rt} self={ent.id} value={r.target ?? `?:${r.text}`} onPick={(id) => mutate(path, (d) => setRelTarget(d, v, i, targetText(snap, id)))} />
                ) : r.target ? (
                  <a className={`ref ${r.target.startsWith("ent:") ? "ref-ent" : "ref-cap"}`} href={href(r.target)}>
                    {label(r.target)}
                  </a>
                ) : (
                  <span className="bad-target">{r.text}</span>
                )}
                {rt?.attrs.map((a) => (
                  <span key={a.name} className="rel-attr">
                    <span className="muted small">{a.name}</span>
                    {own ? (
                      <Field
                        label={`${v} ${a.name}`}
                        ui={resolveUi(ui, "relation", `${v}.${a.name}`, a)}
                        value={r.attrs[a.name] ?? null}
                        fallback={a.default}
                        emptyLabel={emptyLabel(undefined, a)}
                        onCommit={(x) => mutate(path, (d) => setRelAttr(d, v, i, a.name, x === null || x === a.default ? null : typed(a.type, x)))}
                      />
                    ) : (
                      <span className="attr">{r.attrs[a.name] ?? a.default ?? "—"}</span>
                    )}
                  </span>
                ))}
                {own ? (
                  <button className="quiet remove" title={`Remove this ${v} relation`} onClick={() => mutate(path, (d) => removeRel(d, v, i))}>
                    Remove
                  </button>
                ) : (
                  r.src && <Via src={r.src} />
                )}
                {r.err && <div className="err-text">{r.err}</div>}
              </div>
            ))}
          </div>
        );
      })}
      {verbs.length ? (
        <div className="rel-add">
          <span className="muted small">Add</span>
          <select aria-label="Relation" value={verb} onChange={(e) => setNewVerb(e.target.value)}>
            {verbs.map((r) => (
              <option key={r.name} value={r.name}>
                {r.name}
              </option>
            ))}
          </select>
          {rtypes.get(verb) && (
            <TargetSelect
              rt={rtypes.get(verb)!}
              self={ent.id}
              value={null}
              placeholder="— pick a target to add —"
              onPick={(id) => mutate(path, (d) => addRel(d, verb, targetText(snap, id)))}
            />
          )}
        </div>
      ) : (
        <p className="muted">No relation type allows a {ent.type} as its source.</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- capability
export function CapabilityForm({ cap }: { cap: Cap }) {
  const { snap, ui, mutate } = useModel();
  const path = cap.src;
  const [child, setChild] = useState("");
  const [confirm, setConfirm] = useState<string | null>(null);
  if (!path) return <p className="muted">This capability has no source file.</p>;
  const defs = new Map(snap.schema.props.map((p) => [p.name, p]));
  const parentPath = cap.path.split("/").slice(0, -1).join("/");
  const ownKids = cap.children.filter((c) => c.src === path);

  return (
    <div className="form">
      <FormBar path={path} />
      <table className="form-grid">
        <tbody>
          <tr>
            <th>name</th>
            <td>
              <NameField
                value={cap.name}
                title="Capability name (relations that point at the old name are not renamed)"
                onCommit={(v) =>
                  mutate(path, (d) => setScalar(d, capOrThrow(d, cap.path), "name", v)) && (location.hash = href("cap:" + (parentPath ? parentPath + "/" : "") + v))
                }
              />
            </td>
          </tr>
        </tbody>
      </table>

      <h4>Properties</h4>
      <table className="form-grid">
        <tbody>
          {cap.props.map((p) => {
            const def = defs.get(p.name)!;
            const local = p.origin === "local";
            const fromFragment = local && !!p.src && p.src !== path;
            return (
              <tr key={p.name}>
                <th title={def.spec}>
                  {p.name}
                  {def.required && <span className="req">*</span>}
                </th>
                <td>
                  <Field
                    label={p.name}
                    ui={resolveUi(ui, "capability", p.name, def)}
                    value={local ? p.value : null}
                    fallback={local ? def.default : p.value}
                    emptyLabel={emptyLabel(local ? undefined : p, def)}
                    clearable={!fromFragment}
                    suggestions={seen(snap, "capability", p.name)}
                    onCommit={(v) => mutate(path, (d) => setProp(d, capOrThrow(d, cap.path), p.name, v === null ? null : typed(def.type, v)))}
                  />
                  {fromFragment && <Via src={p.src!} />}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!!cap.extra.length && <p className="err-text">Unknown properties (edit the YAML to remove): {cap.extra.join(", ")}</p>}

      <h4>Children</h4>
      <ul className="plain kids">
        {cap.children.map((c) => (
          <li key={c.id}>
            <a className="ref ref-cap" href={href(c.id)}>
              {c.name}
            </a>
            {c.src !== path ? (
              <span className="muted small">defined in {c.src}</span>
            ) : confirm === c.id ? (
              <>
                <button className="danger" onClick={() => mutate(path, (d) => removeChildCap(d, cap.path, c.name)) && setConfirm(null)}>
                  Remove {c.name}
                  {c.children.length ? ` and ${c.children.length} below it` : ""}
                </button>
                <button onClick={() => setConfirm(null)}>Keep</button>
              </>
            ) : (
              <button className="quiet remove" onClick={() => setConfirm(c.id)}>
                Remove…
              </button>
            )}
          </li>
        ))}
      </ul>
      <form
        className="rel-add"
        onSubmit={(e) => {
          e.preventDefault();
          if (child.trim() && mutate(path, (d) => addChildCap(d, cap.path, child.trim(), uuid()))) setChild("");
        }}
      >
        <input placeholder={`New child of ${cap.name}`} aria-label="New child capability" value={child} onChange={(e) => setChild(e.target.value)} />
        <button type="submit" disabled={!child.trim() || cap.children.some((c) => c.name === child.trim())}>
          Add child
        </button>
        {!ownKids.length && !!cap.children.length && <span className="muted small">existing children live in other files</span>}
      </form>
    </div>
  );
}

// ---------------------------------------------------------------- Forms page: which control edits which field
interface Row {
  scope: Scope;
  key: string;
  def: PropDef;
  where: string;
}

function rows(snap: Snapshot): [string, Row[]][] {
  const ents = new Map<string, Row>();
  for (const t of snap.schema.entityTypes)
    for (const p of t.props) {
      const r = ents.get(p.name);
      if (r) r.where += `, ${t.name}`;
      else ents.set(p.name, { scope: "entity", key: p.name, def: p, where: t.name });
    }
  return [
    [`${snap.schema.root} properties`, snap.schema.props.map((p) => ({ scope: "capability" as Scope, key: p.name, def: p, where: "every capability" }))],
    ["Entity properties", [...ents.values()]],
    [
      "Relation attributes",
      snap.schema.relationTypes.flatMap((rt) => rt.attrs.map((a) => ({ scope: "relation" as Scope, key: `${rt.name}.${a.name}`, def: a, where: rt.name }))),
    ],
  ];
}

export function FormsView() {
  const { snap, ui, uiText, saveUi } = useModel();
  const [err, setErr] = useState<string | null>(null);
  const groups = rows(snap);
  const write = (r: Row, u: FieldUi | null) => {
    try {
      setErr(null);
      saveUi(setFieldUi(uiText, r.scope, r.key, u, r.def));
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  return (
    <div className="stack">
      <article className="card">
        <header className="card-head">
          <span className="kind kind-Schema">Forms</span>
          <h2>Field controls</h2>
          <div className="sub">
            Choose the control that edits each field in the entity and capability forms (turn on <b>Edit form</b> on any entity or capability).
            Saved to <span className="mono">model/ui.yaml</span>; the model itself is not changed. Enum fields default to a drop-down.
          </div>
        </header>
        {uiText === null && <p className="banner warn">Could not read ui.yaml; changes may overwrite it.</p>}
        {err && <p className="banner bad">{err}</p>}
      </article>
      {groups.map(([title, rs]) => (
        <article key={title} className="card">
          <h3 className="forms-h">{title}</h3>
          <table className="grid forms">
            <thead>
              <tr>
                <th>field</th>
                <th>type</th>
                <th>control</th>
                <th>settings</th>
                <th>preview</th>
              </tr>
            </thead>
            <tbody>
              {rs.map((r) => (
                <ControlRow key={r.scope + r.key} row={r} ui={ui} onChange={(u) => write(r, u)} />
              ))}
            </tbody>
          </table>
        </article>
      ))}
    </div>
  );
}

function ControlRow({ row, ui, onChange }: { row: Row; ui: UiConfig; onChange: (u: FieldUi | null) => void }) {
  const { def } = row;
  const cfg = lookup(ui, row.scope, row.key);
  const res = resolveUi(ui, row.scope, row.key, def);
  const chosen = cfg.control && controlsFor(def).includes(cfg.control) ? cfg.control : res.base;
  const [opts, setOpts] = useState((cfg.options ?? []).join(", "));
  const [lastOpts, setLastOpts] = useState(cfg.options);
  if (lastOpts !== cfg.options) {
    setLastOpts(cfg.options);
    setOpts((cfg.options ?? []).join(", "));
  }
  const [demo, setDemo] = useState<string | null>(null);
  const parsedOpts = (s: string) =>
    s
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);

  const set = (control: Control, extra: Partial<FieldUi> = {}) => {
    const next: FieldUi = { control, ...extra };
    if (!def.enum && (needsOptions(control) || control === "combo")) next.options = extra.options ?? cfg.options ?? parsedOpts(opts);
    if (control === "slider") Object.assign(next, { min: cfg.min ?? 0, max: cfg.max ?? 365, step: cfg.step ?? 1, ...extra });
    const isDefault = control === res.base && !next.options?.length && control !== "slider";
    onChange(isDefault ? null : next);
  };
  const missingOptions = !def.enum && needsOptions(chosen) && !(cfg.options ?? []).length;

  return (
    <tr>
      <td>
        <span className="mono">{row.key}</span>
        <div className="muted small">{row.where}</div>
      </td>
      <td className="small">{def.enum ? `enum: ${def.enum.join(" | ")}` : def.type}</td>
      <td>
        <select aria-label={`Control for ${row.key}`} value={chosen} onChange={(e) => set(e.target.value as Control)}>
          {controlsFor(def).map((c) => (
            <option key={c} value={c}>
              {CONTROL_LABEL[c]}
              {c === res.base ? " (default)" : ""}
            </option>
          ))}
        </select>
      </td>
      <td className="settings">
        {!def.enum && (needsOptions(chosen) || chosen === "combo") && (
          <label>
            <span className="muted small">{chosen === "combo" ? "suggestions" : "choices"}</span>
            <input
              aria-label={`Choices for ${row.key}`}
              placeholder={def.type === "int" ? "e.g. 30, 60, 90" : "comma-separated"}
              value={opts}
              onChange={(e) => setOpts(e.target.value)}
              onBlur={() => parsedOpts(opts).join(",") !== (cfg.options ?? []).join(",") && set(chosen, { options: parsedOpts(opts) })}
              onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
            />
          </label>
        )}
        {chosen === "slider" &&
          (["min", "max", "step"] as const).map((k) => (
            <label key={k}>
              <span className="muted small">{k}</span>
              <input
                type="number"
                className="num"
                aria-label={`${k} for ${row.key}`}
                defaultValue={cfg[k] ?? (k === "min" ? 0 : k === "max" ? 365 : 1)}
                onBlur={(e) => e.target.value !== "" && Number(e.target.value) !== cfg[k] && set("slider", { [k]: Number(e.target.value) })}
              />
            </label>
          ))}
        {missingOptions && <span className="err-text">add choices, or the form falls back to {CONTROL_LABEL[res.base].toLowerCase()}</span>}
      </td>
      <td className="preview-cell">
        <Field ui={res} value={demo} fallback={def.default} emptyLabel={emptyLabel(undefined, def)} onCommit={setDemo} label={`Preview of ${row.key}`} />
      </td>
    </tr>
  );
}
