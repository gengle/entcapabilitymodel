import { useState } from "react";
import { fileHref, groupBy, href, locateUid, looksLikeUid, useModel, type Route } from "./model";
import { IdMatches } from "./views";
import type { Cap } from "./types";

type Tab = "files" | "caps" | "ents";

function storedTab(): Tab {
  try {
    const t = localStorage.getItem("sem.tab");
    return t === "caps" || t === "ents" ? t : "files";
  } catch {
    return "files";
  }
}

export function Sidebar({ route, active, onCreate }: { route: Route; active: string | null; onCreate: (type: string, name: string) => void }) {
  const [tab, setTabState] = useState<Tab>(storedTab);
  const [filter, setFilter] = useState("");
  const setTab = (t: Tab) => {
    setTabState(t);
    try {
      localStorage.setItem("sem.tab", t);
    } catch {
      /* per-viewer convenience only */
    }
  };
  const f = filter.trim().toLowerCase();
  const routeId = route.k === "ent" || route.k === "cap" ? route.id : null;
  return (
    <aside className="sidebar">
      <div className="tabs" role="tablist">
        {(["files", "caps", "ents"] as Tab[]).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
            {t === "files" ? "Files" : t === "caps" ? "Capabilities" : "Entities"}
          </button>
        ))}
      </div>
      <input className="filter" placeholder="Filter, or paste an id…" value={filter} onChange={(e) => setFilter(e.target.value)} />
      <nav className="side-list">
        {looksLikeUid(f) && <IdSearch text={f} />}
        {tab === "files" && <Files f={f} active={active} />}
        {tab === "caps" && <Caps f={f} routeId={routeId} />}
        {tab === "ents" && <Ents f={f} routeId={routeId} onCreate={onCreate} />}
      </nav>
    </aside>
  );
}

/** Objects whose id matches what is typed in the filter, whichever tab is open. */
function IdSearch({ text }: { text: string }) {
  const { idx } = useModel();
  const hits = locateUid(idx, text);
  return (
    <div className="dir id-search">
      <div className="dir-name">Id {hits.length ? `matches (${hits.length})` : "— no match"}</div>
      {hits.length > 0 && <IdMatches hits={hits} />}
    </div>
  );
}

const KIND_LETTER: Record<string, string> = { Model: "M", Schema: "S", Capability: "C", Entity: "E", fragment: "F" };

function Files({ f, active }: { f: string; active: string | null }) {
  const { snap, idx, dirty } = useModel();
  const files = snap.files.filter((x) => !f || x.path.toLowerCase().includes(f));
  const dirOf = (p: string) => (p.includes("/") ? p.slice(0, p.lastIndexOf("/") + 1) : "");
  return (
    <>
      {groupBy(files, (x) => dirOf(x.path)).map(([dir, xs]) => (
        <div key={dir} className="dir">
          {dir && <div className="dir-name">{dir}</div>}
          {xs.map((x) => {
            const issues = idx.issuesByFile.get(x.path) ?? [];
            const err = issues.some((i) => i.level === "error");
            return (
              <a
                key={x.path}
                href={fileHref(x.path)}
                className={`side-item${x.path === active ? " on" : ""}${x.reached ? "" : " dim"}`}
                title={x.reached ? x.path : `${x.path} (not included from the model)`}
              >
                <span className={`kind-letter kind-${x.kind}`}>{KIND_LETTER[x.kind] ?? "?"}</span>
                <span className="grow">{x.path.slice(dir.length)}</span>
                {dirty.has(x.path) && <span className="dirty-dot" title="unsaved changes" />}
                {!!issues.length && <span className={`issue-dot ${err ? "error" : "warning"}`} title={`${issues.length} issue(s)`} />}
              </a>
            );
          })}
        </div>
      ))}
    </>
  );
}

function Caps({ f, routeId }: { f: string; routeId: string | null }) {
  const { snap } = useModel();
  const match = (c: Cap): boolean => !f || c.name.toLowerCase().includes(f) || c.children.some(match);
  const render = (cs: Cap[], depth: number) =>
    cs.filter(match).map((c) => (
      <div key={c.id}>
        <a href={href(c.id)} className={`side-item${c.id === routeId ? " on" : ""}`} style={{ paddingLeft: 10 + depth * 14 }}>
          <span className={`dot dot-${c.status ?? "none"}`} />
          <span className="grow">{c.name}</span>
        </a>
        {render(c.children, depth + 1)}
      </div>
    ));
  return <>{render(snap.capabilities, 0)}</>;
}

function Ents({ f, routeId, onCreate }: { f: string; routeId: string | null; onCreate: (type: string, name: string) => void }) {
  const { snap } = useModel();
  const types = snap.schema.entityTypes.map((t) => t.name);
  const [name, setName] = useState("");
  const [type, setType] = useState(types[0] ?? "");
  const ents = snap.entities.filter((e) => !f || e.name.toLowerCase().includes(f) || e.type.toLowerCase().includes(f));
  return (
    <>
      {groupBy(ents, (e) => e.type).map(([t, es]) => (
        <div key={t} className="dir">
          <div className="dir-name">{t}</div>
          {es.map((e) => (
            <a key={e.id} href={href(e.id)} className={`side-item${e.id === routeId ? " on" : ""}`}>
              <span className="grow">{e.name}</span>
              <span className="muted small">{e.relations.length}</span>
            </a>
          ))}
        </div>
      ))}
      <form
        className="new-entity"
        onSubmit={(ev) => {
          ev.preventDefault();
          if (name.trim()) onCreate(type, name.trim());
          setName("");
        }}
      >
        <div className="dir-name">New entity</div>
        <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <div className="row">
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {types.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
          <button type="submit" disabled={!name.trim()}>
            Create
          </button>
        </div>
      </form>
    </>
  );
}
