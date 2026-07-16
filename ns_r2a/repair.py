"""Counterexample-guided repair loop.

Runs L1 then L2 on the candidate model; if violations exist, they are
rendered into a repair prompt (current model JSON + concrete
counterexamples) and the LLM produces a patched model. Repeats up to
`max_repairs` rounds. L1 must be clean before L2 runs, since the
symbolic encoding assumes declared endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .l1_graph import L1_RULES, check_structure
from .l2_verify import verify
from .llm import LLMBackend
from .schemas import ArchitectureModel, RequirementSet, Violation

REPAIR_SYSTEM = """\
You are a software architect fixing formal verification failures in an
architecture model. You will receive the current model as JSON and a list of
violations, each with a concrete counterexample. Return the FULL corrected
model as JSON. Change only what is needed to fix the violations; preserve all
valid components, connectors, and traces. Never fix a violation by deleting a
requirement trace unless the trace itself is the problem.\
"""


@dataclass
class RepairRound:
    round_number: int
    violations: list[Violation]


@dataclass
class PipelineResult:
    model: ArchitectureModel
    verified: bool
    rounds: list[RepairRound] = field(default_factory=list)
    remaining_violations: list[Violation] = field(default_factory=list)
    rules_checked: list[str] = field(default_factory=list)


def check_all(model: ArchitectureModel, requirements: RequirementSet) -> list[Violation]:
    l1 = check_structure(model, requirements)
    if l1:
        return l1
    return verify(model, requirements).violations


def _repair_prompt(model: ArchitectureModel, violations: list[Violation]) -> str:
    rendered = "\n".join(v.render() for v in violations)
    return (
        f"Current architecture model:\n{model.model_dump_json(indent=2)}\n\n"
        f"Verification failed with these violations:\n{rendered}\n\n"
        "Return the full corrected model as JSON."
    )


def repair_loop(
    model: ArchitectureModel,
    requirements: RequirementSet,
    backend: LLMBackend,
    max_repairs: int = 3,
    on_round=None,
) -> PipelineResult:
    rules = L1_RULES + verify(model, requirements).rules_checked
    rounds: list[RepairRound] = []
    current = model

    for round_number in range(max_repairs + 1):
        violations = check_all(current, requirements)
        if not violations:
            return PipelineResult(
                model=current, verified=True, rounds=rounds, rules_checked=rules
            )
        rounds.append(RepairRound(round_number=round_number, violations=violations))
        if on_round:
            on_round(round_number, violations)
        if round_number == max_repairs:
            break
        current = backend.generate(
            REPAIR_SYSTEM, _repair_prompt(current, violations), ArchitectureModel
        )

    return PipelineResult(
        model=current,
        verified=False,
        rounds=rounds,
        remaining_violations=rounds[-1].violations,
        rules_checked=rules,
    )
