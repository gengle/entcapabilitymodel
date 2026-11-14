import { Fragment, useState } from "react";
import { api } from "./api";
import { CapabilityForm, EntityForm, targetText } from "./forms";
import { addRel } from "./yamledit";
import { fileHref, groupBy, href, label, useModel } from "./model";
import { entityDefs, FieldName, HelpCard, RefValue, useOpenHelp } from "./help";
import type { Cap, Ent, FileInfo, Incoming, PropDef, RelationType, Snapshot, Issue, PropVal, Status } from "./types";

// ---------------------------------------------------------------- small pieces
export function Ref({ id }: { id: string }) {
  const { idx } = useModel();
  const exists = id.startsWith("ent:") ? idx.ents.has(id) : idx.caps.has(id);
  return (
    <a className={`ref ${id.startsWith("ent:") ? "ref-ent" : "ref-cap"}${exists ? "" : " missing"}`} href={href(id)} title={id.slice(4)}>
      {label(id)}
    </a>
  );
}

export function FileLink({ path }: { path: string }) {
  return (
    <a className="file-link" href={fileHref(path)}>
      {path}
    </a>
  );
}

/** "via <file>" when a value came from a different file than the object it belongs to (i.e. a fragment). */
function Via({ src, home }: { src: string | null; home: string | null }) {
  if (!src || src === home) return null;
  return (
    <a className="via" href={fileHref(src)} title="merged in from this file">
      via {src.split("/").pop()}
    </a>
  );
}

const STATUS: Record<Exclude<Status, null>, string> = { ok: "covered", white: "white space", overlap: "overlap" };

/** What each coverage status means (badge tooltips, the Overview legend and the Schema page). */
export const STATUS_HELP: Record<Exclude<Status, null>, string> = {
  ok: "At least one active entity provides this capability, directly or through a capability beneath it.",
  overlap: "Two or more entities provide this capability directly. Check whether that is intended redundancy or duplication.",
  white:
    "A gap: no active entity provides this capability or anything beneath it. Add a provider, or retire the capability if the business no longer needs it.",
};

export function StatusBadge({ status }: { status: Status }) {
  return status ? (
    <span className={`status status-${status}`} title={STATUS_HELP[status]}>
      {STATUS[status]}
    </span>
  ) : null;
}

function Attrs({ attrs }: { attrs: Record<string, string> }) {
  const e = Object.entries(attrs);
  return e.length ? (
    <span className="attrs">
      {e.map(([k, v]) => (
        <span key={k} className="attr">
          {k}={v}
        </span>
      ))}
    </span>
  ) : null;
}

export function Issues({ issues }: { issues: Issue[] }) {
  if (!issues.length) return null;
  return (
    <ul className="issues">
      {issues.map((i, n) => (
        <li key={n} className={`issue issue-${i.level}`}>
          <span className="issue-level">{i.level}</span> {i.msg}
          {i.file && (
            <>
              {" "}
              <FileLink path={i.file} />
            </>
          )}
        </li>
      ))}
    </ul>
  );
}

function Section({ title, children, count }: { title: string; children: React.ReactNode; count?: number }) {
  return (
    <section className="section">
      <h3>
        {title}
        {count !== undefined && <span className="count">{count}</span>}
      </h3>
      {children}
    </section>
  );
}

/** The universal id, shortened; click copies the full UUID. */
function Uid({ uid }: { uid: string | null }) {
  const [copied, setCopied] = useState(false);
  if (!uid) return <span className="uid missing" title="No id yet: use Assign ids on the Overview, or run python sem.py ids">no id</span>;
  const copy = () => {
    try {
      navigator.clipboard?.writeText(uid).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1200);
      });
    } catch {
      /* clipboard needs a secure context; the full id is still in the tooltip */
    }
  };
  return (
    <button className="uid" title={`${uid} (click to copy)`} onClick={copy}>
      {copied ? "copied" : `id ${uid.slice(0, 8)}…`}
    </button>
  );
}

function FormToggle() {
  const { formMode, setFormMode } = useModel();
  return (
    <button className={`mode-btn${formMode ? " on" : ""}`} aria-pressed={formMode} onClick={() => setFormMode(!formMode)}>
      {formMode ? "Done editing" : "Edit form"}
    </button>
  );
}

function IncomingList({ items }: { items: Incoming[] }) {
  const { idx } = useModel();
  if (!items.length) return <p className="muted">Nothing points here.</p>;
  return (
    <dl className="rels">
      {groupBy(items, (i) => i.inverse).map(([inv, xs]) => (
        <div key={inv} className="rel-group">
          <dt>{inv}</dt>
          {xs.map((x, n) => (
            <dd key={n}>
              <Ref id={x.from} /> <Attrs attrs={x.attrs} /> <Via src={x.src} home={idx.ents.get(x.from)?.src ?? null} />
            </dd>
          ))}
        </div>
      ))}
    </dl>
  );
}

// ---------------------------------------------------------------- entity
export function EntityView({ ent }: { ent: Ent }) {
  const { idx, snap, formMode } = useModel();
  const file = idx.files.get(ent.src);
  const rtypes = new Map(snap.schema.relationTypes.map((r) => [r.name, r]));
  return (
    <article className="card">
      <header className="card-head">
        <span className="kind kind-Entity">{ent.type}</span>
        <h2>{ent.name}</h2>
        {ent.retired && <span className="status status-white">retired</span>}
        <span className="grow" />
        <FormToggle />
        <div className="sub">
          is-a {ent.chain.join(" › ") || "?"} · defined in <FileLink path={ent.src} /> <Uid uid={ent.uid} />
        </div>
      </header>
      <Issues issues={(idx.issuesByFile.get(ent.src) ?? []).filter((i) => i.msg.includes(ent.name))} />
      {!!file?.includes.length && (
        <div className="includes">
          includes{" "}
          {file.includes.map((p) => (
            <FileLink key={p} path={p} />
          ))}
        </div>
      )}
      {formMode ? (
        <Section title="Edit">
          <EntityForm ent={ent} />
        </Section>
      ) : (
        <>
      <Section title="Properties">
        <PropsTable props={ent.props} home={ent.src} defs={entityDefs(snap, ent.chain)} />
      </Section>
      <Section title="Relations" count={ent.relations.length}>
        {ent.relations.length ? (
          <dl className="rels">
            {groupBy(ent.relations, (r) => r.verb).map(([verb, rs]) => (
              <div key={verb} className="rel-group">
                <dt>
                  {verb}
                  {rtypes.get(verb)?.inverse && <span className="muted"> (inverse {rtypes.get(verb)!.inverse})</span>}
                </dt>
                {rs.map((r, n) => (
                  <dd key={n} className={r.err ? "bad" : ""}>
                    {r.target ? <Ref id={r.target} /> : <span className="bad-target">{r.text}</span>} <Attrs attrs={r.attrs} />{" "}
                    <Via src={r.src} home={ent.src} />
                    {r.err && <div className="err-text">{r.err}</div>}
                  </dd>
                ))}
              </div>
            ))}
          </dl>
        ) : (
          <p className="muted">No relations.</p>
        )}
      </Section>
        </>
      )}
      <Section title="Pointing here">
        <IncomingList items={ent.incoming} />
      </Section>
      <ImpactPanel ent={ent} />
    </article>
  );
}

/** Comma-separated refs; `extra` adds a muted note after an item (e.g. hop count). */
function RefList({ ids, extra }: { ids: string[]; extra?: (id: string) => string | null }) {
  return (
    <>
      {ids.map((id, n) => (
        <span key={id}>
          {n > 0 && ", "}
          <Ref id={id} />
          {extra?.(id) && <span className="muted"> {extra(id)}</span>}
        </span>
      ))}
    </>
  );
}

const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;

/** What retiring this entity would change. Comes from the snapshot, so it follows unsaved drafts too. */
function ImpactPanel({ ent }: { ent: Ent }) {
  const { provides, white, unmet, dependents, referenced } = ent.impact;
  const hard = unmet.filter((u) => u.dependency === "hard").length;
  const nDeps = dependents.reduce((a, d) => a + d.affected.length, 0);
  const provided = new Set(provides.map((p) => p.target));
  const extraWhite = white.filter((w) => !provided.has(w));
  const whiteSet = new Set(white);

  const effects = [
    white.length && `leaves ${plural(white.length, "capability", "capabilities")} without a provider`,
    hard && `breaks ${plural(hard, "hard requirement")}`,
    unmet.length - hard && `leaves ${plural(unmet.length - hard, "soft requirement")} unmet`,
    nDeps && `affects ${plural(nDeps, "dependent")}`,
    referenced.length && `leaves ${plural(referenced.length, "item")} pointing at a retired ${groupBy(referenced, (r) => r.prop).map(([p]) => p).join(" / ")}`,
  ].filter(Boolean) as string[];
  const level = white.length || hard ? "bad" : effects.length ? "warn" : "ok";
  const headline = ent.retired
    ? "Already retired"
    : level === "ok"
      ? "Safe to retire"
      : level === "bad"
        ? "Retiring it breaks the model"
        : "Retiring it needs follow-up";
  const detail = ent.retired
    ? "It no longer counts as a provider" + (nDeps ? `, but ${plural(nDeps, "entity", "entities")} still depend on it.` : ".")
    : effects.length
      ? `Retiring ${ent.name} ${effects.join(", ").replace(/, ([^,]*)$/, " and $1")}.`
      : provides.length
        ? "Everything it provides is also provided by something else, and nothing depends on it."
        : "It provides no capabilities and nothing depends on it.";

  return (
    <Section title="Retirement impact">
      <div className={`verdict verdict-${ent.retired ? "muted" : level}`}>
        <b>{headline}</b>
        <span>{detail}</span>
      </div>
      {(provides.length > 0 || extraWhite.length > 0 || unmet.length > 0 || nDeps > 0 || referenced.length > 0) && (
        <dl className="impact">
          {provides.length > 0 && (
            <>
              <dt>Provides</dt>
              <dd>
                <ul className="plain">
                  {provides.map((p) => (
                    <li key={p.target}>
                      <Ref id={p.target} />{" "}
                      {p.others.length ? (
                        <span className="muted">
                          also by <RefList ids={p.others} />
                        </span>
                      ) : (
                        <span className={`status ${whiteSet.has(p.target) ? "status-white" : "status-overlap"}`}>sole provider</span>
                      )}
                    </li>
                  ))}
                </ul>
              </dd>
            </>
          )}
          {extraWhite.length > 0 && (
            <>
              <dt>Also left uncovered</dt>
              <dd>
                <RefList ids={extraWhite} />
              </dd>
            </>
          )}
          {unmet.length > 0 && (
            <>
              <dt>Requirements left unmet</dt>
              <dd>
                <ul className="plain">
                  {unmet.map((u, n) => (
                    <li key={n}>
                      <Ref id={u.entity} /> <span className="muted">{u.verb}</span> <Ref id={u.target} />{" "}
                      <span className={`status ${u.dependency === "hard" ? "status-white" : "status-warn"}`}>{u.dependency}</span>
                    </li>
                  ))}
                </ul>
              </dd>
            </>
          )}
          {groupBy(referenced, (r) => r.prop).map(([prop, rs]) => (
            <div key={prop} className="impact-row">
              <dt>{prop} of</dt>
              <dd>
                <RefList ids={rs.map((r) => r.from)} />
              </dd>
            </div>
          ))}
          {dependents.map((d) => (
            <div key={d.relation} className="impact-row">
              <dt>
                {d.inverse ?? d.relation} <span className="muted">(via {d.relation})</span>
              </dt>
              <dd>
                <RefList
                  ids={d.affected.map((a) => a.id)}
                  extra={(id) => {
                    const h = d.affected.find((a) => a.id === id)!.hops;
                    return h > 1 ? `(${h} hops)` : null;
                  }}
                />
              </dd>
            </div>
          ))}
        </dl>
      )}
    </Section>
  );
}

function PropsTable({ props, home, defs }: { props: PropVal[]; home: string | null; defs: Map<string, PropDef> }) {
  const help = useOpenHelp();
  return (
    <table className="props">
      <tbody>
        {props.map((p) => {
          const def = defs.get(p.name);
          return (
            <Fragment key={p.name}>
              <tr className={p.origin === "local" ? "local" : ""}>
                <th>
                  <FieldName name={p.name} def={def} open={help.isOpen(p.name)} onToggle={() => help.toggle(p.name)} />
                </th>
                <td className="val">
                  {p.value == null ? <span className="muted">—</span> : def?.type === "ref" ? <RefValue def={def} value={p.value} refId={p.ref} /> : p.value}
                  {def && p.value != null && def.valueDocs[p.value] && <div className="value-doc">{def.valueDocs[p.value]}</div>}
                </td>
                <td className="origin">
                  <Origin p={p} home={home} />
                </td>
              </tr>
              {def && help.isOpen(p.name) && (
                <tr className="help-row">
                  <td colSpan={3}>
                    <HelpCard def={def} current={p.value} />
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

/** Schema page: each prop with its spec, description and the meaning of each value. */
function PropDocs({ props }: { props: PropDef[] }) {
  if (!props.length) return <span className="muted">—</span>;
  return (
    <div className="prop-docs">
      {props.map((p) => (
        <div key={p.name}>
          <span className="mono small">
            {p.name}: {p.spec.slice(p.spec.indexOf(":") + 1).trim()}
          </span>
          {p.description && <div className="small">{p.description}</div>}
          {(p.enum ?? []).some((v) => p.valueDocs[v]) && (
            <dl className="value-docs compact">
              {(p.enum ?? []).map((v) => (
                <div key={v}>
                  <dt>{v}</dt>
                  <dd>{p.valueDocs[v] ?? <span className="muted">No description.</span>}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      ))}
    </div>
  );
}

function Origin({ p, home }: { p: PropVal; home: string | null }) {
  if (p.origin.startsWith("inherited from ")) {
    const path = p.origin.slice("inherited from ".length);
    return (
      <>
        inherited from <Ref id={"cap:" + path} />
      </>
    );
  }
  if (p.origin.startsWith("invalid")) return <span className="err-text">{p.origin}</span>;
  if (p.origin === "local" && p.src && p.src !== home) return <Via src={p.src} home={home} />;
  return <span className={p.origin === "local" ? "" : "muted"}>{p.origin === "local" ? "set here" : p.origin}</span>;
}

// ---------------------------------------------------------------- providers
/** Relation types that provide a capability (named in some relation's satisfied_by, e.g. exposes). */
function providerVerbs(snap: Snapshot): RelationType[] {
  const names = new Set(snap.schema.relationTypes.flatMap((r) => r.satisfiedBy));
  return snap.schema.relationTypes.filter((r) => names.has(r.name));
}

/** Pick an entity to provide this capability: adds e.g. `exposes: [<capability>]` to that entity's file as an unsaved draft. */
function AddProvider({ cap }: { cap: Cap }) {
  const { snap, mutateFile } = useModel();
  const verbs = providerVerbs(snap).filter((r) => !r.minLevel || cap.level >= r.minLevel);
  const [verbName, setVerb] = useState("");
  const rt = verbs.find((r) => r.name === verbName) ?? verbs[0];
  if (!rt) return null;
  const allowed = (e: Ent) => rt.from.includes("*") || e.chain.some((t) => rt.from.includes(t));
  const already = (e: Ent) => e.relations.some((r) => r.verb === rt.name && r.target === cap.id);
  const conflict = (e: Ent) => e.relations.find((r) => rt.conflictsWith.includes(r.verb) && r.target === cap.id)?.verb;
  const candidates = snap.entities.filter((e) => allowed(e) && !already(e));
  if (!candidates.length) return null;
  const add = (name: string) => {
    const e = snap.entities.find((x) => x.name === name);
    if (e) mutateFile(e.src, (d) => addRel(d, rt.name, targetText(snap, cap.id)));
  };
  return (
    <div className="rel-add add-provider">
      <span className="muted small">Add a provider</span>
      {verbs.length > 1 && (
        <select aria-label="Relation" value={rt.name} onChange={(e) => setVerb(e.target.value)}>
          {verbs.map((r) => (
            <option key={r.name} value={r.name} title={r.description ?? undefined}>
              {r.name}
            </option>
          ))}
        </select>
      )}
      <select aria-label="Provider" value="" onChange={(e) => e.target.value && add(e.target.value)}>
        <option value="">— pick an entity that {rt.name} it —</option>
        {groupBy(candidates, (e) => e.type).map(([type, es]) => (
          <optgroup key={type} label={type}>
            {es.map((e) => {
              const c = conflict(e);
              return (
                <option key={e.id} value={e.name} disabled={!!c || e.retired}>
                  {e.name}
                  {e.retired ? " (retired)" : c ? ` (it ${c} this)` : ""}
                </option>
              );
            })}
          </optgroup>
        ))}
      </select>
    </div>
  );
}

/** Providers added from this page that are still unsaved drafts in their own file: save or discard them here. */
function PendingProviders({ cap }: { cap: Cap }) {
  const { dirty, saveFile, revert, idx } = useModel();
  const pending = cap.providers.map((id) => idx.ents.get(id)).filter((e): e is Ent => !!e && dirty.has(e.src));
  if (!pending.length) return null;
  return (
    <ul className="plain pending">
      {pending.map((e) => (
        <li key={e.id}>
          <Ref id={e.id} /> <span className="muted small">unsaved change in</span> <FileLink path={e.src} />{" "}
          <button className="primary small-btn" onClick={() => saveFile(e.src)}>
            Save
          </button>{" "}
          <button className="small-btn" title={`Discard all unsaved changes to ${e.src}`} onClick={() => revert(e.src)}>
            Discard
          </button>
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------- capability
export function CapabilityView({ cap }: { cap: Cap }) {
  const { idx, snap, formMode } = useModel();
  const parts = cap.path.split("/");
  const direct = new Set(cap.providers);
  const below = cap.rolledProviders.filter((p) => !direct.has(p));
  return (
    <article className="card">
      <header className="card-head">
        <span className="kind kind-Capability">
          L{cap.level} {cap.levelName}
        </span>
        <h2>{cap.name}</h2>
        <StatusBadge status={cap.status} />
        <span className="grow" />
        {cap.src && <FormToggle />}
        <div className="sub crumbs">
          {parts.slice(0, -1).map((_, i) => (
            <span key={i}>
              <Ref id={"cap:" + parts.slice(0, i + 1).join("/")} /> ›{" "}
            </span>
          ))}
          {cap.name}
          {cap.src && (
            <>
              {" "}
              · defined in <FileLink path={cap.src} />
            </>
          )}{" "}
          <Uid uid={cap.uid} />
        </div>
      </header>
      <Issues issues={(idx.issuesByFile.get(cap.src ?? "") ?? []).filter((i) => i.msg.startsWith(cap.path + ":") || i.msg.includes(" " + cap.path + " "))} />
      {formMode && cap.src ? (
        <Section title="Edit">
          <CapabilityForm cap={cap} />
        </Section>
      ) : (
        <Section title="Properties">
          <PropsTable props={cap.props} home={cap.src} defs={new Map(snap.schema.props.map((p) => [p.name, p]))} />
          {!!cap.extra.length && <p className="err-text">Unknown properties: {cap.extra.join(", ")}</p>}
        </Section>
      )}
      <Section title="Provided by" count={cap.rolledProviders.length}>
        {cap.rolledProviders.length ? (
          <>
            {cap.providers.map((id) => (
              <Ref key={id} id={id} />
            ))}
            {!!below.length && (
              <div className="muted">
                via sub-capabilities:{" "}
                {below.map((id) => (
                  <Ref key={id} id={id} />
                ))}
              </div>
            )}
          </>
        ) : cap.status === "white" ? (
          <div className="warn-box white-help">
            <b>White space.</b> No active entity provides this capability or anything beneath it, so it is a gap in the model.
            Pick the application, service or team that delivers it below, or retire the capability if it is no longer needed.
          </div>
        ) : (
          <p className="muted">No active entity provides this.</p>
        )}
        <PendingProviders cap={cap} />
        {cap.status !== null && <AddProvider cap={cap} />}
      </Section>
      <Section title="Pointing here">
        <IncomingList items={cap.incoming} />
      </Section>
      {!!cap.children.length && !(formMode && cap.src) && (
        <Section title="Children" count={cap.children.length}>
          <CapTree caps={cap.children} />
        </Section>
      )}
    </article>
  );
}

export function CapTree({ caps }: { caps: Cap[] }) {
  return (
    <ul className="tree">
      {caps.map((c) => (
        <li key={c.id}>
          <span className={`dot dot-${c.status ?? "none"}`} />
          <Ref id={c.id} />
          <span className="muted small">
            {" "}
            L{c.level}
            {c.rolledProviders.length ? ` · ${c.rolledProviders.length} provider${c.rolledProviders.length > 1 ? "s" : ""}` : ""}
          </span>
          {!!c.children.length && <CapTree caps={c.children} />}
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------- files
export function FileView({ file }: { file: FileInfo }) {
  const { idx } = useModel();
  const issues = idx.issuesByFile.get(file.path) ?? [];
  return (
    <div className="stack">
      <article className="card">
        <header className="card-head">
          <span className={`kind kind-${file.kind}`}>{file.kind}</span>
          <h2 className="mono">{file.path}</h2>
        </header>
        {!file.reached && (
          <p className="warn-box">Not reached from the model's includes, so it is ignored. Add it to an `include:` (directly or by glob).</p>
        )}
        <Issues issues={issues} />
        <div className="file-links">
          {!!file.includes.length && (
            <div>
              includes{" "}
              {file.includes.map((p) => (
                <FileLink key={p} path={p} />
              ))}
            </div>
          )}
          {!!file.includedBy.length && (
            <div>
              included by{" "}
              {file.includedBy.map((p) => (
                <FileLink key={p} path={p} />
              ))}
            </div>
          )}
        </div>
        {file.kind === "fragment" && <FragmentUse file={file} />}
        {file.kind === "Model" && <ModelSummary />}
      </article>
      {file.kind === "Schema" && <SchemaView />}
      {file.defines.map((id) => {
        const e = idx.ents.get(id);
        const c = idx.caps.get(id);
        return e ? <EntityView key={id} ent={e} /> : c ? <CapabilityView key={id} cap={c} /> : null;
      })}
    </div>
  );
}

function FragmentUse({ file }: { file: FileInfo }) {
  const { snap } = useModel();
  const users = snap.entities
    .map((e) => ({ e, props: e.props.filter((p) => p.src === file.path), rels: e.relations.filter((r) => r.src === file.path) }))
    .filter((u) => u.props.length || u.rels.length);
  return (
    <Section title="Contributes" count={users.length}>
      {users.length ? (
        <ul className="plain">
          {users.map(({ e, props, rels }) => (
            <li key={e.id}>
              <Ref id={e.id} />:{" "}
              {props.map((p) => (
                <span key={p.name} className="attr">
                  {p.name}={p.value}
                </span>
              ))}
              {rels.map((r, n) => (
                <span key={n}>
                  {" "}
                  {r.verb} {r.target ? <Ref id={r.target} /> : r.text}
                </span>
              ))}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">This fragment currently adds nothing (an including file overrides every value, or nothing includes it).</p>
      )}
    </Section>
  );
}

function VersionControl() {
  const { snap, run, dirty } = useModel();
  const v = snap.model.version;
  const [text, setText] = useState("");
  const set = (to: string) => run(api.setVersion(to), `Model version set`).then((ok) => ok && setText(""));
  return (
    <Section title="Model version">
      <div className="version-row">
        <span className="version-now">{v ? `v${v}` : <span className="muted">not set</span>}</span>
        {v && /^\d+\.\d+\.\d+/.test(v) && (
          <>
            <button onClick={() => set("patch")} title="Fixes and small edits">
              Bump patch
            </button>
            <button onClick={() => set("minor")} title="New capabilities, entities or relations">
              Bump minor
            </button>
            <button onClick={() => set("major")} title="Breaking changes (renames, removals, schema changes)">
              Bump major
            </button>
          </>
        )}
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim()) set(text.trim());
          }}
        >
          <input aria-label="Set version" placeholder={v ? "or set e.g. 2.0.0" : "e.g. 1.0.0"} value={text} onChange={(e) => setText(e.target.value)} />
          <button type="submit" disabled={!text.trim()}>
            Set
          </button>
        </form>
      </div>
      {dirty.has(snap.entry) && <p className="muted small">model.yaml has unsaved edits in the editor; a version change writes the file directly.</p>}
    </Section>
  );
}

function ModelSummary() {
  const { snap } = useModel();
  const kinds = groupBy(snap.files.filter((f) => f.reached), (f) => f.kind);
  return (
    <>
    <VersionControl />
    <Section title="Reached files">
      <ul className="plain">
        {kinds.map(([k, fs]) => (
          <li key={k}>
            <span className={`kind kind-${k}`}>{k}</span> {fs.length}
          </li>
        ))}
      </ul>
    </Section>
    </>
  );
}

// ---------------------------------------------------------------- schema
export function SchemaView() {
  const { snap } = useModel();
  const s = snap.schema;
  return (
    <article className="card">
      <header className="card-head">
        <span className="kind kind-Schema">Schema</span>
        <h2>{s.root} tree</h2>
        <div className="sub">
          {Object.entries(s.levels).map(([k, v], i) => (
            <span key={k}>
              {i > 0 && " › "}L{k} {v}
            </span>
          ))}
        </div>
      </header>
      <Section title="Capability properties">
        <table className="grid">
          <thead>
            <tr>
              <th>name</th>
              <th>type</th>
              <th>default</th>
              <th>flags</th>
              <th>meaning</th>
            </tr>
          </thead>
          <tbody>
            {s.props.map((p) => (
              <tr key={p.name}>
                <td className="mono">{p.name}</td>
                <td>{p.enum ? p.enum.join(" | ") : p.type}</td>
                <td>{p.default ?? ""}</td>
                <td className="muted">{[p.inherit && "inherit", p.required && "required"].filter(Boolean).join(", ")}</td>
                <td className="small">
                  {p.description}
                  {(p.enum ?? []).some((v) => p.valueDocs[v]) && (
                    <dl className="value-docs compact">
                      {(p.enum ?? []).map((v) => (
                        <div key={v}>
                          <dt>{v}</dt>
                          <dd>{p.valueDocs[v] ?? <span className="muted">No description.</span>}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!!Object.keys(s.rules).length && (
          <p className="muted">
            rules:{" "}
            {Object.entries(s.rules)
              .map(([k, v]) => (v ? `${k} (${v})` : k))
              .join(", ")}
          </p>
        )}
      </Section>
      <Section title="Coverage">
        <p className="small">
          Capabilities at L{snap.coverage.minLevel} and below get a coverage status. An entity provides a capability through{" "}
          {providerVerbs(snap).map((r) => r.name).join(" or ") || "a relation named in some satisfied_by"}; a capability also counts the
          providers of the capabilities beneath it. Retired entities don't count.
        </p>
        <dl className="value-docs">
          {(["ok", "overlap", "white"] as const).map((k) => (
            <div key={k}>
              <dt>
                <span className={`status status-${k}`}>{STATUS[k]}</span>
              </dt>
              <dd>{STATUS_HELP[k]}</dd>
            </div>
          ))}
        </dl>
      </Section>
      <Section title="Entity types">
        <table className="grid">
          <thead>
            <tr>
              <th>type</th>
              <th>extends</th>
              <th>own props</th>
              <th>effective</th>
            </tr>
          </thead>
          <tbody>
            {s.entityTypes.map((t) => (
              <tr key={t.name}>
                <td>
                  <b>{t.name}</b>
                  {t.description && <div className="small muted">{t.description}</div>}
                </td>
                <td>{t.parent ?? ""}</td>
                <td>
                  <PropDocs props={t.props} />
                </td>
                <td className="muted">{t.effective.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
      <Section title="Relation types">
        <table className="grid">
          <thead>
            <tr>
              <th>relation</th>
              <th>shape</th>
              <th>inverse</th>
              <th>attrs</th>
              <th>rules</th>
            </tr>
          </thead>
          <tbody>
            {s.relationTypes.map((r) => (
              <tr key={r.name}>
                <td>
                  <b>{r.name}</b>
                  {r.description && <div className="small muted">{r.description}</div>}
                </td>
                <td>
                  {r.from.join("|")} → {r.to.join("|")}
                </td>
                <td>{r.inverse ?? ""}</td>
                <td>
                  <PropDocs props={r.attrs} />
                </td>
                <td className="muted small">
                  {[
                    r.minLevel && `L${r.minLevel}+`,
                    r.satisfiedBy.length && `satisfied by ${r.satisfiedBy.join(", ")}`,
                    r.conflictsWith.length && `conflicts with ${r.conflictsWith.join(", ")}`,
                    r.transitive && "transitive",
                    r.noCycles && "no cycles",
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
    </article>
  );
}

// ---------------------------------------------------------------- overview
function countMissingIds(snap: import("./types").Snapshot) {
  let n = snap.entities.filter((e) => !e.uid).length;
  const walk = (c: Cap) => {
    if (!c.uid) n++;
    c.children.forEach(walk);
  };
  snap.capabilities.forEach(walk);
  return n;
}

export function Overview() {
  const { snap, run } = useModel();
  const missing = countMissingIds(snap);
  const errs = snap.issues.filter((i) => i.level === "error").length;
  const warns = snap.issues.length - errs;
  const c = snap.coverage;
  return (
    <div className="stack">
      <div className="stats">
        <Stat n={snap.entities.length} label="entities" />
        <Stat n={snap.files.filter((f) => f.reached).length} label="files" />
        <Stat n={`${c.covered}/${c.total}`} label={`covered at L${c.minLevel}+`} />
        <Stat n={errs} label="errors" tone={errs ? "bad" : "good"} />
        <Stat n={warns} label="warnings" tone={warns ? "warn" : "good"} />
      </div>
      {!!missing && (
        <p className="banner warn">
          {missing} capabilit{missing === 1 ? "y" : "ies"}/entit{missing === 1 ? "y" : "ies"} without a universal id.{" "}
          <button onClick={() => run(api.assignIds(), `Assigned ${missing} id${missing === 1 ? "" : "s"}`)}>Assign ids</button>{" "}
          <span className="muted small">writes an `id:` line under each name; unsaved edits in the editor stay as drafts</span>
        </p>
      )}
      {!!snap.issues.length && (
        <article className="card">
          <Section title="Validation" count={snap.issues.length}>
            <Issues issues={snap.issues} />
          </Section>
        </article>
      )}
      {!!snap.gaps.length && (
        <article className="card">
          <Section title="Unmet requirements" count={snap.gaps.length}>
            <ul className="plain">
              {snap.gaps.map((g, n) => (
                <li key={n}>
                  <Ref id={g.entity} /> {g.verb} <Ref id={g.target} /> <span className="muted">({g.dependency}) — nothing {g.satisfiedBy.join("/")} it</span>
                </li>
              ))}
            </ul>
          </Section>
        </article>
      )}
      <article className="card">
        <Section title="Capability coverage">
          <div className="legend">
            <span title={STATUS_HELP.ok}>
              <span className="dot dot-ok" /> covered
            </span>
            <span title={STATUS_HELP.overlap}>
              <span className="dot dot-overlap" /> overlap (2+ direct providers)
            </span>
            <span title={STATUS_HELP.white}>
              <span className="dot dot-white" /> white space (nothing provides it)
            </span>
            <span>
              <span className="dot dot-none" /> above L{c.minLevel}
            </span>
          </div>
          <CapTree caps={snap.capabilities} />
        </Section>
      </article>
    </div>
  );
}

function Stat({ n, label, tone }: { n: number | string; label: string; tone?: string }) {
  return (
    <div className={`stat ${tone ?? ""}`}>
      <div className="stat-n">{n}</div>
      <div className="stat-l">{label}</div>
    </div>
  );
}

// ---------------------------------------------------------------- id lookup
/** #/id/<uuid>: shown only when the id matches no object or several (one match redirects to it). */
export function IdView({ uid, hits }: { uid: string; hits: (Cap | Ent)[] }) {
  return (
    <article className="card">
      <header className="card-head">
        <span className="kind kind-Schema">Id</span>
        <h2 className="mono">{uid}</h2>
      </header>
      {hits.length === 0 ? (
        <p className="muted">
          No capability or entity has an id matching <span className="mono">{uid}</span>. Give the full id or at least 4 hex digits.
        </p>
      ) : (
        <>
          <p className="muted">{hits.length} objects have ids starting with this; pick one or give more digits.</p>
          <IdMatches hits={hits} />
        </>
      )}
    </article>
  );
}

/** A list of objects found by id: link, what it is, its file and full id. */
export function IdMatches({ hits }: { hits: (Cap | Ent)[] }) {
  return (
    <ul className="plain id-hits">
      {hits.map((x) => (
        <li key={x.id}>
          <Ref id={x.id} /> <span className="muted small">{"type" in x ? x.type : `L${x.level} ${x.levelName}`}</span>
          <div className="mono small muted">
            {x.uid} · {x.src}
          </div>
        </li>
      ))}
    </ul>
  );
}
