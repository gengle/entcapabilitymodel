// Shapes returned by server.py (see snapshot() there). Ids are "cap:<path>" or "ent:<name>".

export interface PropDef {
  name: string;
  type: string;
  enum: string[] | null;
  default: string | null;
  inherit: boolean;
  required: boolean;
  spec: string;
  description: string | null; // what the field means (schema `description`)
  valueDocs: Record<string, string>; // enum value -> what it means (schema `values` mapping)
  to: string[] | null; // type ref: the entity types a value may point at
  key: boolean; // the value identifies its entity, so a ref may use it (e.g. a User's email)
}

export interface PropVal {
  name: string;
  value: string | null;
  origin: string; // capabilities: local | inherited from <path> | root default | unset; entities: local | default | unset | unknown
  src: string | null;
  ref: string | null; // type ref: the entity ("ent:<name>") the value points at, null when it matches none
}

export interface Incoming {
  verb: string;
  inverse: string;
  from: string;
  attrs: Record<string, string>;
  src: string | null;
}

export type Status = "ok" | "white" | "overlap" | null;

export interface Cap {
  id: string;
  uid: string | null; // universal id (YAML `id`, a UUID); survives renames
  name: string;
  path: string;
  level: number;
  levelName: string;
  src: string | null;
  props: PropVal[];
  extra: string[];
  providers: string[];
  rolledProviders: string[];
  status: Status;
  incoming: Incoming[];
  children: Cap[];
}

export interface Rel {
  verb: string;
  text: string;
  target: string | null;
  label: string;
  attrs: Record<string, string>;
  src: string | null;
  err: string | null;
}

export interface Ent {
  id: string;
  uid: string | null;
  name: string;
  type: string;
  chain: string[];
  src: string;
  retired: boolean;
  props: PropVal[];
  relations: Rel[];
  incoming: Incoming[];
  impact: Impact; // what retiring this entity would change (sem.impact); computed per snapshot, so drafts count
}

export interface FileInfo {
  path: string;
  kind: string; // Model | Schema | Capability | Entity | fragment
  includes: string[];
  includedBy: string[];
  reached: boolean;
  defines: string[];
}

export interface Issue {
  level: "error" | "warning";
  msg: string;
  file: string | null;
}

export interface Gap {
  entity: string;
  verb: string;
  target: string;
  dependency: string;
  satisfiedBy: string[];
}

export interface EntityType {
  name: string;
  parent: string | null;
  chain: string[];
  props: PropDef[];
  effective: string[];
  description: string | null;
}

export interface RelationType {
  name: string;
  from: string[];
  to: string[];
  attrs: PropDef[];
  inverse: string | null;
  minLevel: number | null;
  satisfiedBy: string[];
  conflictsWith: string[];
  transitive: boolean;
  noCycles: boolean;
  description: string | null;
}

export interface Snapshot {
  entry: string;
  version?: string; // hash of the files on disk (live reload), not the model version
  model: { name: string | null; version: string | null };
  schema: {
    root: string;
    levels: Record<string, string>;
    props: PropDef[];
    rules: Record<string, string>;
    entityTypes: EntityType[];
    relationTypes: RelationType[];
  };
  capabilities: Cap[];
  entities: Ent[];
  files: FileInfo[];
  issues: Issue[];
  gaps: Gap[];
  coverage: { minLevel: number; total: number; covered: number };
}

export interface Impact {
  provides: { target: string; others: string[] }[]; // capabilities it provides directly, with the providers left
  white: string[]; // capabilities (at or above the coverage level) left with no provider
  unmet: { entity: string; verb: string; target: string; dependency: string }[]; // requirements that would become unmet
  dependents: { relation: string; inverse: string | null; affected: { id: string; hops: number }[] }[];
  referenced: { from: string; prop: string }[]; // ref props that name this entity (what it owns, heads, ...)
}
