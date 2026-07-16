"""L0a: normalize a natural-language requirements document into a RequirementSet."""

from __future__ import annotations

from .llm import LLMBackend
from .schemas import RequirementSet

SYSTEM = """\
You are a requirements engineer. Extract atomic requirements from the document.

Rules:
- One requirement per distinct obligation; split compound sentences.
- Assign sequential ids R1, R2, ...
- kind: 'functional' for behavior the system must perform, 'non_functional'
  for qualities (performance, security, availability), 'constraint' for
  imposed technology/regulatory limits.
- actors: the roles or external systems involved.
- entities: the domain objects (nouns) the requirement is about.
- Keep 'text' faithful to the source; normalize to "The system shall ..." form.
- Do not invent requirements that are not in the document.\
"""


def normalize(document: str, backend: LLMBackend) -> RequirementSet:
    prompt = f"Extract the requirements from this document:\n\n{document}"
    return backend.generate(SYSTEM, prompt, RequirementSet)
