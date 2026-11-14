// Shapes returned by server.py (see snapshot() there). Ids are "cap:<path>" or "ent:<name>".

export interface PropDef {
  name: string;
  type: string;
  enum: string[] | null;
  default: string | null;
  inherit: boolean;
  required: boolean;
  spec: string;
}

export interface PropVal {
  name: string;
  value: string | null;
  origin: string; // capabilities: local | inherited from <path> | root default | unset; entities: local | default | unset | unknown
  src: string | null;
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
  name: string;
  type: string;
  chain: string[];
  src: string;
  retired: boolean;
  props: PropVal[];
  relations: Rel[];
  incoming: Incoming[];
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
}

export interface Snapshot {
  entry: string;
  version?: string;
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
  entity: string;
  lostCapabilities: string[];
  newUnmet: { entity: string; verb: string; target: string; dependency: string }[];
  transitive: { relation: string; affected: { id: string; hops: number }[] }[];
}
