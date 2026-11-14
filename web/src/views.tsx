import { useState } from "react";
import { api } from "./api";
import { fileHref, groupBy, href, label, useModel } from "./model";
import type { Cap, Ent, FileInfo, Impact, Incoming, Issue, PropVal, Status } from "./types";

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

export function StatusBadge({ status }: { status: Status }) {
  return status ? <span className={`status status-${status}`}>{STATUS[status]}</span> : null;
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
  const { idx, snap } = useModel();
  const file = idx.files.get(ent.src);
  const rtypes = new Map(snap.schema.relationTypes.map((r) => [r.name, r]));
  return (
    <article className="card">
      <header className="card-head">
        <span className="kind kind-Entity">{ent.type}</span>
        <h2>{ent.name}</h2>
        {ent.retired && <span className="status status-white">retired</span>}
        <div className="sub">
          is-a {ent.chain.join(" › ") || "?"} · defined in <FileLink path={ent.src} />
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
      <Section title="Properties">
        <PropsTable props={ent.props} home={ent.src} />
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
      <Section title="Pointing here">
        <IncomingList items={ent.incoming} />
      </Section>
      <ImpactPanel name={ent.name} />
    </article>
  );
}

function ImpactPanel({ name }: { name: string }) {
  const [res, setRes] = useState<Impact | string | null>(null);
  const run = () => api.impact(name).then(setRes, (e: Error) => setRes(e.message));
  return (
    <Section title="Impact">
      {res === null ? (
        <button onClick={run}>What breaks if {name} is retired?</button>
      ) : typeof res === "string" ? (
        <p className="err-text">{res}</p>
      ) : (
        <div className="impact">
          <p className="muted">Based on the saved files.</p>
          <div>
            <b>Capabilities left with no provider:</b>{" "}
            {res.lostCapabilities.length ? res.lostCapabilities.map((id) => <Ref key={id} id={id} />) : <span className="muted">none</span>}
          </div>
          <div>
            <b>Requirements that become unmet:</b>{" "}
            {res.newUnmet.length ? (
              <ul>
                {res.newUnmet.map((u, n) => (
                  <li key={n}>
                    <Ref id={u.entity} /> {u.verb} <Ref id={u.target} /> <span className="muted">({u.dependency})</span>
                  </li>
                ))}
              </ul>
            ) : (
              <span className="muted">none</span>
            )}
          </div>
          {res.transitive.map((t) => (
            <div key={t.relation}>
              <b>Affected via {t.relation} (transitive):</b>{" "}
              {t.affected.map((a) => (
                <span key={a.id}>
                  <Ref id={a.id} />
                  {a.hops > 1 && <span className="muted"> ({a.hops} hops)</span>}{" "}
                </span>
              ))}
            </div>
          ))}
          <button className="link-btn" onClick={() => setRes(null)}>
            clear
          </button>
        </div>
      )}
    </Section>
  );
}

function PropsTable({ props, home }: { props: PropVal[]; home: string | null }) {
  return (
    <table className="props">
      <tbody>
        {props.map((p) => (
          <tr key={p.name} className={p.origin === "local" ? "local" : ""}>
            <th>{p.name}</th>
            <td className="val">{p.value ?? <span className="muted">—</span>}</td>
            <td className="origin">
              <Origin p={p} home={home} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
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

// ---------------------------------------------------------------- capability
export function CapabilityView({ cap }: { cap: Cap }) {
  const { idx } = useModel();
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
          )}
        </div>
      </header>
      <Issues issues={(idx.issuesByFile.get(cap.src ?? "") ?? []).filter((i) => i.msg.startsWith(cap.path + ":") || i.msg.includes(" " + cap.path + " "))} />
      <Section title="Properties">
        <PropsTable props={cap.props} home={cap.src} />
        {!!cap.extra.length && <p className="err-text">Unknown properties: {cap.extra.join(", ")}</p>}
      </Section>
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
        ) : (
          <p className="muted">No active entity provides this{cap.status === "white" ? " (white space)" : ""}.</p>
        )}
      </Section>
      <Section title="Pointing here">
        <IncomingList items={cap.incoming} />
      </Section>
      {!!cap.children.length && (
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

function ModelSummary() {
  const { snap } = useModel();
  const kinds = groupBy(snap.files.filter((f) => f.reached), (f) => f.kind);
  return (
    <Section title="Reached files">
      <ul className="plain">
        {kinds.map(([k, fs]) => (
          <li key={k}>
            <span className={`kind kind-${k}`}>{k}</span> {fs.length}
          </li>
        ))}
      </ul>
    </Section>
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
            </tr>
          </thead>
          <tbody>
            {s.props.map((p) => (
              <tr key={p.name}>
                <td className="mono">{p.name}</td>
                <td>{p.enum ? p.enum.join(" | ") : p.type}</td>
                <td>{p.default ?? ""}</td>
                <td className="muted">{[p.inherit && "inherit", p.required && "required"].filter(Boolean).join(", ")}</td>
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
                </td>
                <td>{t.parent ?? ""}</td>
                <td className="mono small">{t.props.map((p) => p.spec).join("; ")}</td>
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
                </td>
                <td>
                  {r.from.join("|")} → {r.to.join("|")}
                </td>
                <td>{r.inverse ?? ""}</td>
                <td className="mono small">{r.attrs.map((p) => p.spec).join("; ")}</td>
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
export function Overview() {
  const { snap } = useModel();
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
            <span>
              <span className="dot dot-ok" /> covered
            </span>
            <span>
              <span className="dot dot-overlap" /> overlap (2+ direct providers)
            </span>
            <span>
              <span className="dot dot-white" /> white space
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
