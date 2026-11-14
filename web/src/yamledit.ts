// Structured edits to model files that keep comments, quoting and layout (the `yaml` Document API).
// Forms call these on a file's draft text; the result goes through the normal preview / save path.
import { Document, isMap, isScalar, isSeq, Pair, parseDocument, Scalar, YAMLMap, YAMLSeq } from "yaml";

export const STRINGIFY = { lineWidth: 0, flowCollectionPadding: false } as const;

export type Edit = (doc: Document) => void;

export function applyEdit(text: string, fn: Edit): string {
  const doc = parseDocument(text);
  if (doc.errors.length) throw new Error(`The file has a YAML error; fix it in the editor first (${doc.errors[0].message})`);
  if (!isMap(doc.contents)) throw new Error("The file is not a YAML mapping");
  fn(doc);
  return doc.toString(STRINGIFY);
}

export const root = (doc: Document) => doc.contents as YAMLMap;

/** The node (not its JS value) under key; typed loosely because the yaml typings assume scalars. */
export const nodeAt = (map: YAMLMap, key: string): unknown => map.get(key, true) as unknown;

/** A JS value for a field: ints stay numbers so `review_cycle_days: 90` is not written as a string. */
export const typed = (type: string, v: string): string | number => (type === "int" && /^-?\d+$/.test(v) ? Number(v) : v);

/** parent[key] as a block mapping, created (before `before`, if that key exists) when missing. */
function block(doc: Document, parent: YAMLMap, key: string, before?: string): YAMLMap {
  let m = nodeAt(parent, key);
  if (!isMap(m)) {
    m = doc.createNode({}) as YAMLMap;
    const at = before ? parent.items.findIndex((p) => isScalar(p.key) && p.key.value === before) : -1;
    if (nodeAt(parent, key) === undefined && at >= 0) parent.items.splice(at, 0, new Pair(doc.createNode(key), m));
    else parent.set(key, m);
  }
  (m as YAMLMap).flow = false;
  return m as YAMLMap;
}

/** Set (or with null, remove) key in map, reusing the existing scalar so its quoting style survives. */
export function setScalar(doc: Document, map: YAMLMap, key: string, v: string | number | null) {
  if (v === null) return void map.delete(key);
  const cur = nodeAt(map, key);
  if (isScalar(cur) && typeof cur.value === typeof v) cur.value = v;
  else map.set(key, doc.createNode(v));
}

export function setProp(doc: Document, owner: YAMLMap, name: string, v: string | number | null) {
  if (v === null) {
    const props = nodeAt(owner, "props");
    if (isMap(props)) {
      props.delete(name);
      // an entity keeps `props: {}` (the file template has it); a capability drops the empty key
      if (!props.items.length && !owner.has("type")) owner.delete("props");
    }
    return;
  }
  setScalar(doc, block(doc, owner, "props", owner.has("children") ? "children" : "relations"), name, v);
}

// ---------------------------------------------------------------- capabilities
/** The mapping for the capability at `path` ("Finance/Accounts Payable/...") inside this file. A file holds a subtree,
 *  so match the longest chain of `name`s that is a suffix of the path. */
export function findCap(doc: Document, path: string): YAMLMap | null {
  const segs = path.split("/");
  let best: YAMLMap | null = null;
  let bestLen = 0;
  const walk = (node: unknown, chain: string[]) => {
    if (!isMap(node)) return;
    const name = node.get("name");
    const c = name == null ? chain : [...chain, String(name)];
    if (name != null && c.length <= segs.length && c.length > bestLen && c.every((s, i) => s === segs[segs.length - c.length + i])) {
      best = node;
      bestLen = c.length;
    }
    const kids = nodeAt(node, "children");
    if (isSeq(kids)) kids.items.forEach((k) => walk(k, c));
  };
  walk(doc.contents, []);
  return best;
}

export function capOrThrow(doc: Document, path: string): YAMLMap {
  const m = findCap(doc, path);
  if (!m) throw new Error(`Cannot find ${path} in this file`);
  return m;
}

export function addChildCap(doc: Document, path: string, name: string, id: string) {
  const m = capOrThrow(doc, path);
  let kids = nodeAt(m, "children");
  if (!isSeq(kids)) {
    kids = doc.createNode([]) as YAMLSeq;
    m.set("children", kids);
  }
  (kids as YAMLSeq).flow = false;
  (kids as YAMLSeq).add(doc.createNode({ name, id }));
}

export function removeChildCap(doc: Document, parentPath: string, name: string) {
  const kids = nodeAt(capOrThrow(doc, parentPath), "children");
  if (!isSeq(kids)) throw new Error(`${name} is not a child in this file`);
  const i = kids.items.findIndex((k) => isMap(k) && String(k.get("name")) === name);
  if (i < 0) throw new Error(`${name} is not a child in this file`);
  kids.items.splice(i, 1);
  if (!kids.items.length) capOrThrow(doc, parentPath).delete("children");
}

// ---------------------------------------------------------------- entity relations
// `i` counts only the entries this file writes under `verb` (entries merged in from fragments live elsewhere).
function verbSeq(doc: Document, verb: string, create: boolean): YAMLSeq | null {
  const root = doc.contents as YAMLMap;
  let rels = nodeAt(root, "relations");
  if (!isMap(rels)) {
    if (!create) return null;
    rels = doc.createNode({}) as YAMLMap;
    root.set("relations", rels);
  }
  const r = rels as YAMLMap;
  r.flow = false;
  let seq = nodeAt(r, verb);
  if (!isSeq(seq)) {
    if (!create && seq == null) return null;
    const single = seq;
    seq = doc.createNode([]) as YAMLSeq;
    if (single != null && !(isScalar(single) && single.value == null)) (seq as YAMLSeq).items.push(single);
    r.set(verb, seq);
  }
  (seq as YAMLSeq).flow = false;
  return seq as YAMLSeq;
}

function item(doc: Document, verb: string, i: number): { seq: YAMLSeq; node: unknown } {
  const seq = verbSeq(doc, verb, false);
  if (!seq || i >= seq.items.length) throw new Error(`No ${verb} entry #${i + 1} in this file`);
  return { seq, node: seq.items[i] };
}

export function setRelTarget(doc: Document, verb: string, i: number, target: string) {
  const { seq, node } = item(doc, verb, i);
  if (isMap(node)) setScalar(doc, node, "target", target);
  else if (isScalar(node)) node.value = target;
  else seq.items[i] = doc.createNode(target);
}

export function setRelAttr(doc: Document, verb: string, i: number, attr: string, v: string | number | null) {
  const { seq, node } = item(doc, verb, i);
  let m: YAMLMap;
  if (isMap(node)) m = node;
  else {
    if (v === null) return;
    m = doc.createNode({ target: isScalar(node) ? node.value : String(node) }) as YAMLMap;
    m.flow = false;
    seq.items[i] = m;
  }
  setScalar(doc, m, attr, v);
  if (m.items.length === 1 && m.has("target")) seq.items[i] = nodeAt(m, "target") as Scalar; // back to the short form
}

export function removeRel(doc: Document, verb: string, i: number) {
  const { seq } = item(doc, verb, i);
  seq.items.splice(i, 1);
  if (!seq.items.length) {
    const rels = nodeAt(doc.contents as YAMLMap, "relations") as YAMLMap;
    rels.delete(verb);
  }
}

export function addRel(doc: Document, verb: string, target: string) {
  verbSeq(doc, verb, true)!.add(doc.createNode(target));
}
