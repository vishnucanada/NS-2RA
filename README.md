# NS-R2A

**Neuro-Symbolic Requirements-to-Architecture**: a local-LLM pipeline that turns a
natural-language requirements document into formally verified architecture views
(PlantUML), in the style of R2ABench. The neural half proposes; the symbolic half
(graph diagnostics + Z3) verifies and produces counterexamples that guide repair.

Everything runs locally: the LLM via [Ollama](https://ollama.com), verification via
the Z3 theorem prover.

## Pipeline

```
requirements.md
   │  L0a  normalize          LLM, JSON-schema-constrained decoding
   ▼
RequirementSet (typed)
   │  L0b  generate           LLM, JSON-schema-constrained decoding
   ▼
ArchitectureModel (typed components / connectors / traces)
   │  L1   graph diagnostics  networkx — edge hallucinations, orphans,
   │                          duplicate ids, invalid type pairs
   │  L2   symbolic checks    Z3 — layering, acyclicity, requirement
   │                          coverage, single entrypoint, interface
   │                          compatibility (unsat cores → counterexamples)
   ▼
violations? ──► counterexample-guided repair prompt ──► LLM patch ──► re-verify
   │ (up to --max-repairs rounds)
   ▼
component.puml · layers.puml · report.md · architecture.json
```

Two design rules make the verification meaningful:

1. **The LLM never writes PlantUML.** It emits a typed JSON model (schema-enforced
   at decode time by Ollama structured outputs); diagrams are rendered
   deterministically from the verified model, so they are always syntactically
   valid and consistent with what was checked.
2. **Violations carry witnesses.** Each failed rule produces a concrete
   counterexample (e.g. the Z3 unsat core naming the exact connectors forming a
   dependency cycle), and that text — not just "verification failed" — is what the
   repair prompt feeds back to the model.

## Quickstart

```bash
python3 -m venv venv && venv/bin/pip install -e '.[dev]'
ollama pull gemma3:4b   # or any model you prefer

venv/bin/ns-r2a generate examples/order_system.md -o out --model gemma3:4b
```

Typical run (gemma3:4b): the first candidate fails several rules, and the loop
converges over a few repair rounds:

```
L0a normalizing requirements with gemma3:4b ...
      11 requirements (7 functional)
L0b generating architecture model ...
      7 components, 6 connectors
L1+L2 verifying (graph diagnostics + Z3) ...
      round 0: 6 violation(s) -> repairing
      round 1: 2 violation(s) -> repairing
      round 2: 1 violation(s) -> repairing
VERIFIED — all rules hold. Outputs in out/
```

Re-verify any saved model without an LLM:

```bash
venv/bin/ns-r2a check out/architecture.json out/requirements.json
```

## Built-in rules

| Level | Rule | Meaning |
|---|---|---|
| L1 | `edge-endpoints-declared` | connectors/traces may only reference declared elements (edge hallucination) |
| L1 | `unique-component-ids`, `no-orphan-components`, `no-self-loops` | basic well-formedness |
| L1 | `valid-type-pairs` | e.g. a database never initiates calls |
| L2 | `layering` | presentation → application → domain → infrastructure; never upward |
| L2 | `acyclicity` | Z3 ordering encoding; unsat core names the cycle |
| L2 | `requirement-coverage` | every functional requirement traced to ≥ 1 component |
| L2 | `single-entrypoint` | exactly one user-facing entry component |
| L2 | `interface-compatibility` | a connector's interface must be provided by its target |

## Tests

```bash
venv/bin/python -m pytest
```

The suite uses a fake LLM backend, so it is deterministic and needs no Ollama.

## Notes

- Name the virtualenv `venv`, **not `.venv`**, if the project lives in an
  iCloud-synced folder (Desktop/Documents): iCloud marks dot-directories'
  contents with the macOS hidden flag, and Python ≥ 3.14 skips hidden `.pth`
  files, silently breaking editable installs.
- Roadmap (not yet implemented): benchmark harness with gold architectures,
  LLM-extracted per-requirement constraints (SAT-LLM style), QLoRA/MLX
  fine-tuning of the backbone.
