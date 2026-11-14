#!/usr/bin/env python3
"""sem.py - a dynamic, self-describing semantic model you can navigate and generate from (std-only).

MODEL      tree | schema | validate [--strict] | show <ref> | export | diff <old.sem> <new.sem>
EDIT       add "L1/L2/L3" [k=v ..] [-p] | set <capability> k=v ..
           entity add <Type> <Name> [k=v ..] | entity set <Name> k=v .. | entity list
           link <Entity> <relation> <target> [k=v ..]   (expose / require are shortcuts) | unlink <Entity> <target>
META       type add <Name> [Parent] | type prop <Type> "key: type [= default]"
           relation add <name> <from|from> <to|to> [inverse=x] [transitive] [no_cycles]
NAVIGATE   locate <id> | neighbors <ref> | closure <ref> <relation> | path <A> <B> | who <ref> | gaps | coverage | impact <Entity>
GENERATE   gen <site|sql|typeql|jsonschema|openapi|mermaid|csv|all> <outdir> [--level N] | yaml <outdir>
YAML       ids [--dry-run]   give every capability and entity without an `id` a new UUID (written into its file)
           version [major|minor|patch|<x.y.z>]   show the model version, bump it, or set it (model.yaml)
<ref> is an entity name, a capability path / unique capability name, or an `id`.
Model: $SEM_MODEL, else ./model/ (YAML, see semyaml.py) if present, else ./model.sem. A YAML model is read-only
here: EDIT and META commands refuse it, edit its files (or use server.py). `yaml <outdir>` converts any model.
"""
import sys

from semmodel.model import *
from semmodel.rules import *
from semmodel.legacy import *
from semmodel.cli import *
from semmodel.cli import main

if __name__ == "__main__":
    main()
