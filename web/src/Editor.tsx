import { useEffect, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { yaml } from "@codemirror/lang-yaml";
import { Issues } from "./views";
import type { Issue } from "./types";

export interface Draft {
  saved: string;
  text: string;
  disk?: string | null; // set when the file changed on disk under unsaved edits (null: deleted)
}

export interface Rejection {
  path: string;
  op: "save" | "delete";
  errors: string[];
}

const extensions = [yaml()];

function useDark() {
  const q = "(prefers-color-scheme: dark)";
  const [dark, setDark] = useState(() => matchMedia(q).matches);
  useEffect(() => {
    const m = matchMedia(q);
    const f = () => setDark(m.matches);
    m.addEventListener("change", f);
    return () => m.removeEventListener("change", f);
  }, []);
  return dark;
}

export function EditorPane(props: {
  path: string;
  draft: Draft | undefined;
  issues: Issue[];
  reject: Rejection | null;
  onChange: (text: string) => void;
  onSave: (force?: boolean) => void;
  onRevert: () => void;
  onDelete: (force?: boolean) => void;
  onDismiss: () => void;
  onTakeDisk: () => void;
}) {
  const { path, draft, issues, reject } = props;
  const dark = useDark();
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEffect(() => setConfirmDelete(false), [path]);
  const dirty = !!draft && draft.text !== draft.saved;
  return (
    <section className="editor">
      <div className="toolbar">
        <span className="mono path" title={path}>
          {path}
        </span>
        {dirty && <span className="badge-dirty">unsaved · previewing</span>}
        <span className="grow" />
        <button onClick={props.onRevert} disabled={!dirty}>
          Revert
        </button>
        <button className="primary" onClick={() => props.onSave()} disabled={!dirty} title="Ctrl+S">
          Save
        </button>
        {confirmDelete ? (
          <>
            <button className="danger" onClick={() => props.onDelete()}>
              Delete file
            </button>
            <button onClick={() => setConfirmDelete(false)}>Keep</button>
          </>
        ) : (
          <button className="quiet" onClick={() => setConfirmDelete(true)} title="Delete this file">
            Delete…
          </button>
        )}
      </div>
      {draft?.disk !== undefined && (
        <div className="banner warn">
          {draft.disk === null ? "This file was deleted on disk." : "This file changed on disk while you were editing."}
          <button onClick={props.onTakeDisk}>{draft.disk === null ? "Discard my edits" : "Load disk version"}</button>
        </div>
      )}
      {reject?.path === path && (
        <div className="banner bad">
          <b>{reject.op === "save" ? "Save" : "Delete"} rejected</b>: it would add {reject.errors.length} validation error
          {reject.errors.length === 1 ? "" : "s"}.
          <ul>
            {reject.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
          <button className="danger" onClick={() => (reject.op === "save" ? props.onSave(true) : props.onDelete(true))}>
            {reject.op === "save" ? "Save anyway" : "Delete anyway"}
          </button>
          <button onClick={props.onDismiss}>Dismiss</button>
        </div>
      )}
      <div className="cm-wrap">
        {draft ? (
          <CodeMirror
            value={draft.text}
            height="100%"
            extensions={extensions}
            theme={dark ? "dark" : "light"}
            onChange={props.onChange}
            basicSetup={{ foldGutter: true, highlightActiveLine: true }}
          />
        ) : (
          <div className="muted pad">Loading…</div>
        )}
      </div>
      {!!issues.length && (
        <div className="diagnostics">
          <Issues issues={issues} />
        </div>
      )}
    </section>
  );
}
