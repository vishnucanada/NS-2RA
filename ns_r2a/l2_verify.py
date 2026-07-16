"""L2: symbolic verification with Z3.

Encoding: the architecture is translated into Z3 facts (layer ranks,
topological order variables, coverage/entrypoint booleans). Each rule
becomes a set of *tracked obligations*; a `check` that comes back unsat
yields an unsat core naming exactly the obligations that cannot hold,
which we translate into concrete counterexamples for the repair prompt.

Cores are drained iteratively (remove the core's assumptions, re-check)
so a single pass reports every violation, not just the first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import z3

from .schemas import (
    LAYER_RANK,
    ArchitectureModel,
    RequirementKind,
    RequirementSet,
    VerificationResult,
    Violation,
)

L2_RULES = [
    "layering",
    "acyclicity",
    "requirement-coverage",
    "single-entrypoint",
    "interface-compatibility",
]


@dataclass
class Obligation:
    """One tracked proof obligation and the violation to emit if it fails."""

    tracker: z3.BoolRef
    formula: z3.BoolRef
    violation: Violation


def _drain_cores(solver: z3.Solver, obligations: list[Obligation]) -> list[Violation]:
    """Check obligations under assumptions, harvesting every unsat core."""
    by_tracker = {ob.tracker.decl().name(): ob for ob in obligations}
    for ob in obligations:
        solver.add(z3.Implies(ob.tracker, ob.formula))

    active = [ob.tracker for ob in obligations]
    violations: list[Violation] = []
    while active and solver.check(*active) == z3.unsat:
        core = solver.unsat_core()
        if not core:
            break
        core_names = {c.decl().name() for c in core}
        for name in sorted(core_names):
            violations.append(by_tracker[name].violation)
        active = [t for t in active if t.decl().name() not in core_names]
    return violations


def _check_layering(model: ArchitectureModel) -> list[Violation]:
    solver = z3.Solver()
    solver.set(unsat_core=True)
    layer_of: dict[str, z3.ArithRef] = {}
    for c in model.components:
        v = z3.Int(f"layer_{c.id}")
        layer_of[c.id] = v
        solver.add(v == LAYER_RANK[c.layer])

    obligations = []
    for i, conn in enumerate(model.connectors):
        src, tgt = model.component(conn.source), model.component(conn.target)
        if not src or not tgt:
            continue
        obligations.append(
            Obligation(
                tracker=z3.Bool(f"layering_{i}"),
                formula=layer_of[conn.source] <= layer_of[conn.target],
                violation=Violation(
                    level="L2",
                    rule="layering",
                    message=(
                        f"Connector {conn.source} -> {conn.target} points upward: "
                        f"{src.layer.value} may not depend on {tgt.layer.value}."
                    ),
                    elements=[conn.source, conn.target],
                    counterexample=(
                        f"layer({conn.source})={LAYER_RANK[src.layer]} "
                        f"({src.layer.value}) > layer({conn.target})="
                        f"{LAYER_RANK[tgt.layer]} ({tgt.layer.value}); dependencies must "
                        f"point downward. Reverse it or introduce an intermediary in the "
                        f"{src.layer.value} layer."
                    ),
                ),
            )
        )
    return _drain_cores(solver, obligations)


def _check_acyclicity(model: ArchitectureModel) -> list[Violation]:
    """Unsat core of `ord(src) < ord(tgt)` over all edges names a cycle."""
    solver = z3.Solver()
    solver.set(unsat_core=True)
    ids = model.component_ids()
    order = {cid: z3.Int(f"ord_{cid}") for cid in ids}

    edges = [
        (i, c) for i, c in enumerate(model.connectors) if c.source in ids and c.target in ids
    ]
    trackers = {}
    for i, conn in edges:
        t = z3.Bool(f"edge_{i}")
        trackers[t.decl().name()] = conn
        solver.add(z3.Implies(t, order[conn.source] < order[conn.target]))

    active = list(trackers)
    violations = []
    while active and solver.check(*[z3.Bool(n) for n in active]) == z3.unsat:
        core = solver.unsat_core()
        if not core:
            break
        core_names = sorted(c.decl().name() for c in core)
        cycle_edges = [trackers[n] for n in core_names]
        cycle_str = ", ".join(f"{c.source} -> {c.target}" for c in cycle_edges)
        involved = sorted({c.source for c in cycle_edges} | {c.target for c in cycle_edges})
        violations.append(
            Violation(
                level="L2",
                rule="acyclicity",
                message=f"Dependency cycle among components: {', '.join(involved)}.",
                elements=involved,
                counterexample=(
                    f"No topological order exists because these connectors form a cycle: "
                    f"{cycle_str}. Break the cycle by removing or inverting one of them "
                    f"(e.g. with events via a queue)."
                ),
            )
        )
        active = [n for n in active if n not in core_names]
    return violations


def _check_coverage(model: ArchitectureModel, requirements: RequirementSet) -> list[Violation]:
    solver = z3.Solver()
    solver.set(unsat_core=True)
    traced = {t.requirement_id for t in model.traces if t.component_id in model.component_ids()}

    obligations = []
    for r in requirements.requirements:
        if r.kind != RequirementKind.functional:
            continue
        covered = z3.Bool(f"covered_{r.id}")
        solver.add(covered == z3.BoolVal(r.id in traced))
        obligations.append(
            Obligation(
                tracker=z3.Bool(f"coverage_{r.id}"),
                formula=covered,
                violation=Violation(
                    level="L2",
                    rule="requirement-coverage",
                    message=f"Functional requirement {r.id} is not traced to any component.",
                    elements=[r.id],
                    counterexample=(
                        f"{r.id} ('{r.text[:80]}') has no trace; add a trace linking it to the "
                        f"component responsible for it."
                    ),
                ),
            )
        )
    return _drain_cores(solver, obligations)


def _check_entrypoint(model: ArchitectureModel) -> list[Violation]:
    solver = z3.Solver()
    solver.set(unsat_core=True)
    entry_bools = []
    for c in model.components:
        b = z3.Bool(f"entry_{c.id}")
        solver.add(b == z3.BoolVal(c.entrypoint))
        entry_bools.append(b)
    if not entry_bools:
        return []

    entrypoints = [c.id for c in model.components if c.entrypoint]
    detail = (
        f"entrypoint components found: {entrypoints or 'none'}; exactly one component "
        f"must have entrypoint=true (the one users reach first)."
    )
    obligations = [
        Obligation(
            tracker=z3.Bool("single_entrypoint"),
            formula=z3.PbEq([(b, 1) for b in entry_bools], 1),
            violation=Violation(
                level="L2",
                rule="single-entrypoint",
                message=f"Expected exactly 1 entrypoint component, found {len(entrypoints)}.",
                elements=entrypoints,
                counterexample=detail,
            ),
        )
    ]
    return _drain_cores(solver, obligations)


def _check_interfaces(model: ArchitectureModel) -> list[Violation]:
    solver = z3.Solver()
    solver.set(unsat_core=True)
    obligations = []
    for i, conn in enumerate(model.connectors):
        tgt = model.component(conn.target)
        if not tgt or not conn.interface or not model.component(conn.source):
            continue
        provided = z3.Bool(f"provides_{i}")
        solver.add(provided == z3.BoolVal(conn.interface in tgt.provides))
        obligations.append(
            Obligation(
                tracker=z3.Bool(f"iface_{i}"),
                formula=provided,
                violation=Violation(
                    level="L2",
                    rule="interface-compatibility",
                    message=(
                        f"Connector {conn.source} -> {conn.target} consumes interface "
                        f"'{conn.interface}' which '{conn.target}' does not provide."
                    ),
                    elements=[conn.source, conn.target],
                    counterexample=(
                        f"'{conn.target}' provides {tgt.provides or 'nothing'}; add "
                        f"'{conn.interface}' to its provides list or use a provided interface."
                    ),
                ),
            )
        )
    return _drain_cores(solver, obligations)


def verify(model: ArchitectureModel, requirements: RequirementSet) -> VerificationResult:
    """Run all built-in symbolic rules; assumes L1 checks already pass."""
    checks: list[Callable[[], list[Violation]]] = [
        lambda: _check_layering(model),
        lambda: _check_acyclicity(model),
        lambda: _check_coverage(model, requirements),
        lambda: _check_entrypoint(model),
        lambda: _check_interfaces(model),
    ]
    violations: list[Violation] = []
    for check in checks:
        violations.extend(check())
    return VerificationResult(violations=violations, rules_checked=list(L2_RULES))
