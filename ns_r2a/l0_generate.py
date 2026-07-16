"""L0b: generate a typed architecture model from a normalized RequirementSet."""

from __future__ import annotations

from .llm import LLMBackend
from .schemas import ArchitectureModel, RequirementSet

SYSTEM = """\
You are a software architect. Design a component architecture satisfying the
given requirements. You must obey these structural rules — they are formally
verified afterwards and violations are rejected:

1. Every connector's source and target must be ids from your component list.
2. Layers are ordered presentation > application > domain > infrastructure.
   Connectors must never point upward (e.g. a domain component must not call
   an application component). Same-layer connectors are allowed.
3. The dependency graph must be acyclic.
4. Exactly one component has entrypoint=true (the user-facing entry).
5. Every functional requirement id must appear in at least one trace,
   and traces may only reference declared component ids and given
   requirement ids.
6. A connector's 'interface' must be listed in the target's 'provides'.
7. Databases never initiate connectors; they only receive them.
8. Use snake_case component ids. Keep the design minimal: no component
   without a requirement-driven purpose.\
"""


def generate_architecture(requirements: RequirementSet, backend: LLMBackend) -> ArchitectureModel:
    req_lines = "\n".join(
        f"- {r.id} [{r.kind.value}] {r.text}" for r in requirements.requirements
    )
    prompt = (
        f"System: {requirements.title}\n\nRequirements:\n{req_lines}\n\n"
        "Produce the architecture model as JSON."
    )
    return backend.generate(SYSTEM, prompt, ArchitectureModel)
