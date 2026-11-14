import { createContext, useContext } from "react";
import type { Cap, Ent, FileInfo, Issue, Snapshot } from "./types";

export type Route =
  | { k: "overview" }
  | { k: "schema" }
  | { k: "file"; path: string }
  | { k: "ent"; id: string }
  | { k: "cap"; id: string };

export function parseHash(hash: string): Route {
  const [kind, ...rest] = hash.replace(/^#\/?/, "").split("/");
  const arg = decodeURIComponent(rest.join("/"));
  if (kind === "schema") return { k: "schema" };
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

export const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export interface Ctx {
  snap: Snapshot;
  idx: Index;
  dirty: Set<string>;
}

export const ModelCtx = createContext<Ctx | null>(null);
export const useModel = () => useContext(ModelCtx)!;
