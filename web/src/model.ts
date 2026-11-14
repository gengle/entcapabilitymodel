import { createContext, useContext } from "react";
import type { Cap, Ent, FileInfo, Issue, Snapshot } from "./types";
import type { UiConfig } from "./ui";
import type { Edit } from "./yamledit";

export type Route =
  | { k: "overview" }
  | { k: "schema" }
  | { k: "forms" }
  | { k: "file"; path: string }
  | { k: "ent"; id: string }
  | { k: "cap"; id: string };

export function parseHash(hash: string): Route {
  const [kind, ...rest] = hash.replace(/^#\/?/, "").split("/");
  const arg = decodeURIComponent(rest.join("/"));
  if (kind === "schema") return { k: "schema" };
  if (kind === "forms") return { k: "forms" };
  if (kind === "file" && arg) return { k: "file", path: arg };
  if (kind === "ent" && arg) return { k: "ent", id: "ent:" + arg };
  if (kind === "cap" && arg) return { k: "cap", id: "cap:" + arg };
  return { k: "overview" };
}

export const href = (id: string) => `#/${id.slice(0, 3)}/${encodeURIComponent(id.slice(4))}`;
export const fileHref = (path: string) => `#/file/${encodeURIComponent(path)}`;
export const label = (id: string) => (id.startsWith("cap:") ? id.slice(4).split("/").pop()! : id.slice(4));

export interface Index {
  ents: Map<string, Ent>;
  caps: Map<string, Cap>;
  files: Map<string, FileInfo>;
  issuesByFile: Map<string, Issue[]>;
}

export function buildIndex(s: Snapshot): Index {
  const caps = new Map<string, Cap>();
  const walk = (c: Cap) => {
    caps.set(c.id, c);
    c.children.forEach(walk);
  };
  s.capabilities.forEach(walk);
  const issuesByFile = new Map<string, Issue[]>();
  for (const i of s.issues) {
    const k = i.file ?? "";
    issuesByFile.set(k, [...(issuesByFile.get(k) ?? []), i]);
  }
  return {
    ents: new Map(s.entities.map((e) => [e.id, e])),
    caps,
    files: new Map(s.files.map((f) => [f.path, f])),
    issuesByFile,
  };
}

export function groupBy<T>(xs: T[], key: (x: T) => string): [string, T[]][] {
  const m = new Map<string, T[]>();
  for (const x of xs) m.set(key(x), [...(m.get(key(x)) ?? []), x]);
  return [...m];
}

/** A random UUID v4 (crypto.randomUUID needs a secure context; getRandomValues does not). */
export function uuid(): string {
  if (typeof crypto.randomUUID === "function" && isSecureContext) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export interface Ctx {
  snap: Snapshot;
  idx: Index;
  dirty: Set<string>;
  ui: UiConfig;
  uiText: string | null; // ui.yaml as on disk ("" when it does not exist yet)
  saveUi: (text: string) => Promise<void>;
  formMode: boolean;
  setFormMode: (on: boolean) => void;
  /** Apply a structured edit to a file's draft (it then previews like a typed edit). False if it could not. */
  mutate: (path: string, edit: Edit) => boolean;
  save: () => void;
  /** Saved snapshot from a server action (assign ids, set version); null on failure (a notice is shown). */
  run: (what: Promise<Snapshot>, done: string) => Promise<boolean>;
}

export const ModelCtx = createContext<Ctx | null>(null);
export const useModel = () => useContext(ModelCtx)!;
