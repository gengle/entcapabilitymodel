import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { EditorPane, type Draft, type Rejection } from "./Editor";
import { buildIndex, href, locateUid, ModelCtx, parseHash, slug, uuid, type Route } from "./model";
import { Sidebar } from "./Sidebar";
import type { Snapshot } from "./types";
import { FormsView } from "./forms";
import { parseUi, UI_FILE } from "./ui";
import { CapabilityView, EntityView, FileView, IdView, Overview, SchemaView } from "./views";
import { applyEdit, type Edit } from "./yamledit";

const POLL_MS = 1500;
const PREVIEW_MS = 250;

function storedFormMode() {
  try {
    return localStorage.getItem("sem.form") === "1";
  } catch {
    return false;
  }
}

export default function App() {
  const [snap, setSnap] = useState<Snapshot | null>(null); // saved state on disk
  const [preview, setPreview] = useState<Snapshot | null>(null); // saved state + unsaved drafts
  const [route, setRoute] = useState<Route>(() => parseHash(location.hash));
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [active, setActive] = useState<string | null>(null);
  const [reject, setReject] = useState<Rejection | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [online, setOnline] = useState(true);
  const [uiText, setUiText] = useState<string | null>(null);
  const [formMode, setFormModeState] = useState(storedFormMode);
  const setFormMode = (on: boolean) => {
    setFormModeState(on);
    try {
      localStorage.setItem("sem.form", on ? "1" : "0");
    } catch {
      /* per-viewer convenience only */
    }
  };
  const draftsRef = useRef(drafts);
  draftsRef.current = drafts;
  const verRef = useRef<string | undefined>(undefined);

  useEffect(() => {
    const f = () => setRoute(parseHash(location.hash));
    addEventListener("hashchange", f);
    return () => removeEventListener("hashchange", f);
  }, []);

  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(null), 4000);
    return () => clearTimeout(t);
  }, [notice]);

  // ---- load + live reload: poll the version, refetch the model and any open files when it changes
  const reload = useCallback(async () => {
    const s = await api.model();
    verRef.current = s.version;
    setSnap(s);
    api.file(UI_FILE).then(
      (f) => setUiText(f.content),
      (e) => setUiText(e instanceof ApiError && e.status === 404 ? "" : null),
    );
    const paths = Object.keys(draftsRef.current);
    const disk = await Promise.all(paths.map((p) => api.file(p).then((f) => f.content, () => null)));
    setDrafts((prev) => {
      const next = { ...prev };
      paths.forEach((p, i) => {
        const d = next[p];
        const c = disk[i];
        if (!d || c === d.saved) return;
        if (d.text === d.saved) {
          if (c === null) delete next[p];
          else next[p] = { saved: c, text: c };
        } else next[p] = { ...d, disk: c };
      });
      return next;
    });
  }, []);

  useEffect(() => {
    reload().catch(() => setOnline(false));
    const t = setInterval(async () => {
      try {
        const { version } = await api.version();
        setOnline(true);
        if (version !== verRef.current) await reload();
      } catch {
        setOnline(false);
      }
    }, POLL_MS);
    return () => clearInterval(t);
  }, [reload]);

  // ---- preview: re-render with every unsaved draft applied
  const dirtyFiles = Object.entries(drafts).filter(([, d]) => d.text !== d.saved);
  const dirtyKey = JSON.stringify(dirtyFiles.map(([p, d]) => [p, d.text]));
  useEffect(() => {
    if (!dirtyFiles.length) {
      setPreview(null);
      return;
    }
    const t = setTimeout(() => {
      api.preview(Object.fromEntries(dirtyFiles.map(([p, d]) => [p, d.text]))).then(setPreview, () => setOnline(false));
    }, PREVIEW_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dirtyKey, snap?.version]);

  const view = preview ?? snap;
  const idx = useMemo(() => (view ? buildIndex(view) : null), [view]);
  const savedIdx = useMemo(() => (snap ? buildIndex(snap) : null), [snap]);
  const ui = useMemo(() => parseUi(uiText), [uiText]);

  // ---- which file the editor shows follows the route
  useEffect(() => {
    if (!idx) return;
    if (route.k === "id") {
      // #/id/<uuid or prefix>: go straight to the one object with that id (replace, so Back skips the id link)
      const hits = locateUid(idx, route.uid);
      if (hits.length === 1) location.replace(href(hits[0].id));
      return setActive(null);
    }
    if (route.k === "overview" || route.k === "schema" || route.k === "forms") return setActive(null);
    const p =
      route.k === "file"
        ? route.path
        : route.k === "ent"
          ? (idx.ents.get(route.id) ?? savedIdx?.ents.get(route.id))?.src
          : (idx.caps.get(route.id) ?? savedIdx?.caps.get(route.id))?.src;
    if (p) setActive(p);
  }, [route, idx, savedIdx]);

  useEffect(() => {
    if (!active || draftsRef.current[active]) return;
    api.file(active).then(
      (f) => setDrafts((d) => (d[active] ? d : { ...d, [active]: { saved: f.content, text: f.content } })),
      (e: Error) => setNotice(e.message),
    );
  }, [active]);

  // ---- actions
  const fail = (e: unknown, path: string, op: Rejection["op"]) => {
    if (e instanceof ApiError && e.status === 422) {
      setReject({ path, op, errors: e.body.errors ?? [] });
      // the rejection banner lives in the editor of the open file; for any other file say it here
      if (path !== active) setNotice(`Not saved ${path}: ${(e.body.errors ?? []).join("; ") || "it would add validation errors"}`);
    } else setNotice((e as Error).message);
  };

  const applySaved = (s: Snapshot) => {
    verRef.current = s.version;
    setSnap(s);
    setReject(null);
  };

  const save = async (force = false, path = active) => {
    const d = path && drafts[path];
    if (!path || !d) return;
    try {
      applySaved(await api.save(path, d.text, force));
      setDrafts((p) => ({ ...p, [path]: { saved: d.text, text: p[path]?.text ?? d.text } }));
      setNotice(`Saved ${path}`);
    } catch (e) {
      fail(e, path, "save");
    }
  };
  const saveRef = useRef(save);
  saveRef.current = save;
  useEffect(() => {
    const f = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        saveRef.current();
      }
    };
    addEventListener("keydown", f);
    return () => removeEventListener("keydown", f);
  }, []);

  const remove = async (force = false) => {
    const path = active;
    if (!path) return;
    try {
      applySaved(await api.remove(path, force));
      setDrafts(({ [path]: _gone, ...rest }) => rest);
      setNotice(`Deleted ${path}`);
      location.hash = "#/";
    } catch (e) {
      fail(e, path, "delete");
    }
  };

  const create = async (type: string, name: string) => {
    const path = `entities/${slug(name) || "entity"}.yaml`;
    if (idx?.files.has(path)) return setNotice(`${path} already exists`);
    const content = `kind: Entity\ntype: ${type}\nname: ${JSON.stringify(name)}\nid: ${uuid()}\nprops: {}\nrelations: {}\n`;
    try {
      applySaved(await api.save(path, content));
      location.hash = href("ent:" + name);
    } catch (e) {
      setNotice(e instanceof ApiError && e.body.errors ? `Not created: ${e.body.errors.join("; ")}` : (e as Error).message);
    }
  };

  const edit = (path: string, patch: (d: Draft) => Draft) => setDrafts((p) => (p[path] ? { ...p, [path]: patch(p[path]) } : p));
  const revert = (path: string) => {
    setReject((r) => (r?.path === path ? null : r));
    edit(path, (d) => ({ saved: d.saved, text: d.saved }));
  };

  // Form edits rewrite the draft text through the yaml Document API, so they preview and save like typed edits.
  const mutate = (path: string, fn: Edit) => {
    const d = draftsRef.current[path];
    if (!d) {
      setNotice(`${path} is still loading`);
      return false;
    }
    try {
      const text = applyEdit(d.text, fn);
      if (text !== d.text) {
        draftsRef.current = { ...draftsRef.current, [path]: { ...d, text } };
        setDrafts(draftsRef.current);
        if (reject?.path === path) setReject(null);
      }
      return true;
    } catch (e) {
      setNotice((e as Error).message);
      return false;
    }
  };

  /** mutate() for any file, loading it as a draft first when it isn't open yet. */
  const mutateFile = async (path: string, fn: Edit) => {
    if (!draftsRef.current[path]) {
      try {
        const f = await api.file(path);
        if (!draftsRef.current[path]) {
          draftsRef.current = { ...draftsRef.current, [path]: { saved: f.content, text: f.content } };
          setDrafts(draftsRef.current);
        }
      } catch (e) {
        setNotice((e as Error).message);
        return false;
      }
    }
    return mutate(path, fn);
  };

  // server actions that write files themselves (assign ids, set version): reload so open editors pick up the new text
  const run = async (what: Promise<Snapshot>, done: string) => {
    try {
      await what;
      await reload();
      setReject(null);
      setNotice(done);
      return true;
    } catch (e) {
      setNotice((e as Error).message);
      return false;
    }
  };

  const saveUi = async (text: string) => {
    try {
      applySaved(await api.save(UI_FILE, text, true));
      setUiText(text);
      setNotice(`Saved ${UI_FILE}`);
    } catch (e) {
      setNotice((e as Error).message);
    }
  };

  if (!view || !idx)
    return <div className="boot">{online ? "Loading model…" : "Cannot reach server.py on /api. Start it with: python server.py"}</div>;

  const dirty = new Set(dirtyFiles.map(([p]) => p));
  const errors = view.issues.filter((i) => i.level === "error").length;
  const warnings = view.issues.length - errors;
  const showEditor = route.k !== "overview" && route.k !== "schema" && route.k !== "forms" && !!active;

  let main: React.ReactNode;
  if (route.k === "overview") main = <Overview />;
  else if (route.k === "schema") main = <SchemaView />;
  else if (route.k === "forms") main = <FormsView />;
  else if (route.k === "id") main = <IdView uid={route.uid} hits={locateUid(idx, route.uid)} />;
  else if (route.k === "file") {
    const f = idx.files.get(route.path);
    main = f ? <FileView file={f} /> : <p className="muted pad">No YAML file {route.path}.</p>;
  } else {
    const e = route.k === "ent" ? idx.ents.get(route.id) : undefined;
    const c = route.k === "cap" ? idx.caps.get(route.id) : undefined;
    const f = active ? idx.files.get(active) : undefined;
    main = e ? (
      <EntityView ent={e} />
    ) : c ? (
      <CapabilityView cap={c} />
    ) : (
      <div className="stack">
        <p className="banner warn">{route.id.slice(4)} does not exist{preview ? " in the preview (renamed or removed by your edits)" : ""}.</p>
        {f && <FileView file={f} />}
      </div>
    );
  }

  return (
    <ModelCtx.Provider
      value={{ snap: view, idx, dirty, ui, uiText, saveUi, formMode, setFormMode, mutate, save: () => saveRef.current(), saveFile: (p: string) => saveRef.current(false, p), revert, mutateFile, run }}
    >
      <div className={`app${showEditor ? "" : " no-editor"}`}>
        <header className="top">
          <a className="brand" href="#/">
            {view.model.name ?? "Semantic model"}
          </a>
          <a
            className={`pill ver${view.model.version ? "" : " none"}`}
            href={`#/file/${encodeURIComponent(view.entry)}`}
            title="Model version (set or bump it on the model.yaml page)"
          >
            {view.model.version ? `v${view.model.version}` : "no version"}
          </a>
          <nav className="topnav">
            <a href="#/" className={route.k === "overview" ? "on" : ""}>
              Overview
            </a>
            <a href="#/schema" className={route.k === "schema" ? "on" : ""}>
              Schema
            </a>
            <a href="#/forms" className={route.k === "forms" ? "on" : ""} title="Choose the control that edits each field">
              Forms
            </a>
          </nav>
          <span className="grow" />
          {preview && <span className="pill preview">preview · {dirty.size} unsaved</span>}
          <a href="#/" className={`pill ${errors ? "bad" : warnings ? "warn" : "good"}`}>
            {errors ? `${errors} error${errors > 1 ? "s" : ""}` : "valid"}
            {warnings ? ` · ${warnings} warning${warnings > 1 ? "s" : ""}` : ""}
          </a>
          <span className={`live ${online ? "on" : "off"}`} title={online ? "watching the model folder" : "server unreachable"}>
            {online ? "live" : "offline"}
          </span>
        </header>
        <Sidebar route={route} active={active} onCreate={create} />
        {showEditor && active && (
          <EditorPane
            path={active}
            draft={drafts[active]}
            issues={idx.issuesByFile.get(active) ?? []}
            reject={reject}
            onChange={(text) => {
              if (reject?.path === active) setReject(null);
              edit(active, (d) => ({ ...d, text }));
            }}
            onSave={save}
            onRevert={() => revert(active)}
            onDelete={remove}
            onDismiss={() => setReject(null)}
            onTakeDisk={() =>
              setDrafts(({ [active]: d, ...rest }) => (d?.disk == null ? rest : { ...rest, [active]: { saved: d.disk, text: d.disk } }))
            }
          />
        )}
        <main className="render">{main}</main>
        {notice && <div className="toast">{notice}</div>}
      </div>
    </ModelCtx.Provider>
  );
}
