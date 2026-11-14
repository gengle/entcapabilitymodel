// Field help from the schema: what a field means (PropDef.description) and what each enum value means (PropDef.valueDocs).
import { useState } from "react";
import { href, label } from "./model";
import type { PropDef, Snapshot } from "./types";

/** Effective prop definitions for an entity type chain (nearest type wins), by name. */
export function entityDefs(snap: Snapshot, chain: string[]): Map<string, PropDef> {
  const types = new Map(snap.schema.entityTypes.map((t) => [t.name, t]));
  const out = new Map<string, PropDef>();
  for (const t of chain) for (const p of types.get(t)?.props ?? []) if (!out.has(p.name)) out.set(p.name, p);
  return out;
}

export const hasHelp = (def: PropDef | undefined) => !!def && (!!def.description || Object.keys(def.valueDocs).length > 0);

/** Plain-text help for a title tooltip: the description, then one line per documented value. */
export function helpText(def: PropDef | undefined): string | undefined {
  if (!hasHelp(def)) return undefined;
  const vals = (def!.enum ?? []).filter((v) => def!.valueDocs[v]).map((v) => `${v}: ${def!.valueDocs[v]}`);
  return [def!.description, ...vals].filter(Boolean).join("\n");
}

/** Where a prop's definition (and so its default) comes from in an entity's type chain, nearest type first. */
export function definingType(snap: Snapshot, chain: string[], name: string): string | null {
  const types = new Map(snap.schema.entityTypes.map((t) => [t.name, t]));
  return chain.find((t) => types.get(t)?.props.some((p) => p.name === name)) ?? null;
}

/** The value that applies and where it comes from, plus its meaning. Shown under a field.
 *  origin is PropVal.origin: "local" | "inherited from <path>" | "root default" | "default" | "unset" | ... */
export function AppliedValue({
  def,
  value,
  origin,
  type,
  refId,
}: {
  def: PropDef | undefined;
  value: string | null;
  origin: string;
  type?: string | null;
  refId?: string | null; // type ref: the entity the value resolves to
}) {
  const doc = value != null ? def?.valueDocs[value] : undefined;
  const local = origin === "local";
  const isRef = def?.type === "ref" && value != null;
  if (local && !doc && !isRef) return null;
  let from: React.ReactNode = null;
  if (origin.startsWith("inherited from ")) {
    const id = "cap:" + origin.slice("inherited from ".length);
    from = (
      <>
        inherited from{" "}
        <a className="ref ref-cap" href={href(id)} title={id.slice(4)}>
          {label(id)}
        </a>
      </>
    );
  } else if (origin === "root default" || origin === "default") {
    from = (
      <>
        default from{" "}
        <a href="#/schema" title="Defined on the Schema page">
          {type ? `the ${type} type` : "the schema"}
        </a>
      </>
    );
  }
  if (value == null || (!from && !doc && !isRef)) return null;
  return (
    <div className="value-doc">
      {isRef ? <RefValue def={def!} value={value} refId={refId ?? null} /> : <b>{value}</b>}
      {from && <> {from}</>}
      {doc && <>: {doc}</>}
    </div>
  );
}

/** A ref prop's value as a link to the entity it names; flagged when it names no entity of an allowed type. */
export function RefValue({ def, value, refId }: { def: PropDef; value: string; refId: string | null }) {
  if (!refId)
    return (
      <span className="bad-ref" title={`Not the name, id or key of any ${(def.to ?? []).join(" or ")}`}>
        {value} <span className="err-text">not a known {(def.to ?? []).join(" or ")}</span>
      </span>
    );
  const name = refId.slice(4);
  return (
    <>
      <a className="ref ref-ent" href={href(refId)} title={`Open ${name}`}>
        {name}
      </a>
      {name.toLowerCase() !== value.toLowerCase() && <span className="muted"> ({value})</span>}
    </>
  );
}

/** Entity names a ref prop may point at, for the form's suggestions. */
export function refChoices(snap: Snapshot, def: PropDef): string[] {
  const to = def.to ?? [];
  return snap.entities.filter((e) => to.includes("*") || e.chain.some((t) => to.includes(t))).map((e) => e.name);
}

/** A field's name; when the schema documents it, the name itself opens the help (hover shows it too). */
export function FieldName({ name, def, required, open, onToggle }: { name: string; def: PropDef | undefined; required?: boolean; open: boolean; onToggle: () => void }) {
  const req = required && <span className="req" title="required">*</span>;
  if (!hasHelp(def))
    return (
      <>
        {name}
        {req}
      </>
    );
  return (
    <>
      <button type="button" className={`field-name${open ? " on" : ""}`} aria-expanded={open} title={open ? "Hide help" : helpText(def)} onClick={onToggle}>
        {name}
      </button>
      {req}
    </>
  );
}

/** Which field's help is open in a table (one at a time). */
export function useOpenHelp() {
  const [open, setOpen] = useState<string | null>(null);
  return { isOpen: (k: string) => open === k, toggle: (k: string) => setOpen((o) => (o === k ? null : k)) };
}

/** The full help for one field: description plus a list of the enum values and what each means. */
export function HelpCard({ def, current }: { def: PropDef; current: string | null }) {
  const vals = def.enum ?? [];
  return (
    <div className="help-card" role="note">
      {def.description && <p>{def.description}</p>}
      {vals.some((v) => def.valueDocs[v]) && (
        <dl className="value-docs">
          {vals.map((v) => (
            <div key={v} className={v === current ? "on" : ""}>
              <dt>
                {v}
                {v === def.default && <span className="muted"> default</span>}
              </dt>
              <dd>{def.valueDocs[v] ?? <span className="muted">No description.</span>}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
