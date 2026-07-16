"""L1: structural graph diagnostics.

Compiles the architecture model into a typed directed graph and runs
deterministic structural checks. The headline check is *edge
hallucination*: connectors or traces that reference elements the model
never declared. These must be fixed before L2's symbolic verification,
which assumes a well-formed graph.
"""

from __future__ import annotations

import networkx as nx

from .schemas import ArchitectureModel, ComponentType, RequirementSet, Violation

# Connections that are structurally nonsensical regardless of layering,
# e.g. a database initiating calls into a UI.
FORBIDDEN_TYPE_PAIRS: set[tuple[ComponentType, ComponentType]] = {
    (ComponentType.database, ComponentType.ui),
    (ComponentType.database, ComponentType.service),
    (ComponentType.database, ComponentType.queue),
    (ComponentType.database, ComponentType.external),
    (ComponentType.queue, ComponentType.ui),
}

L1_RULES = [
    "edge-endpoints-declared",
    "trace-endpoints-declared",
    "unique-component-ids",
    "no-orphan-components",
    "no-self-loops",
    "valid-type-pairs",
]


def build_graph(model: ArchitectureModel) -> nx.MultiDiGraph:
    """Typed component graph; only edges with declared endpoints are added."""
    g = nx.MultiDiGraph()
    for c in model.components:
        g.add_node(c.id, layer=c.layer, type=c.type, entrypoint=c.entrypoint)
    ids = model.component_ids()
    for conn in model.connectors:
        if conn.source in ids and conn.target in ids:
            g.add_edge(conn.source, conn.target, interface=conn.interface, protocol=conn.protocol)
    return g


def check_structure(
    model: ArchitectureModel, requirements: RequirementSet | None = None
) -> list[Violation]:
    violations: list[Violation] = []
    ids = model.component_ids()

    seen: set[str] = set()
    for c in model.components:
        if c.id in seen:
            violations.append(
                Violation(
                    level="L1",
                    rule="unique-component-ids",
                    message=f"Component id '{c.id}' is declared more than once.",
                    elements=[c.id],
                    counterexample=f"Two components share the id '{c.id}'; merge or rename one.",
                )
            )
        seen.add(c.id)

    for conn in model.connectors:
        for endpoint in (conn.source, conn.target):
            if endpoint not in ids:
                violations.append(
                    Violation(
                        level="L1",
                        rule="edge-endpoints-declared",
                        message=(
                            f"Connector {conn.source} -> {conn.target} references "
                            f"undeclared component '{endpoint}' (edge hallucination)."
                        ),
                        elements=[conn.source, conn.target],
                        counterexample=(
                            f"'{endpoint}' appears in a connector but is not in the component "
                            f"list. Either declare it as a component or remove the connector."
                        ),
                    )
                )
        if conn.source == conn.target and conn.source in ids:
            violations.append(
                Violation(
                    level="L1",
                    rule="no-self-loops",
                    message=f"Component '{conn.source}' has a connector to itself.",
                    elements=[conn.source],
                    counterexample=f"Remove the self-referencing connector on '{conn.source}'.",
                )
            )

    req_ids = {r.id for r in requirements.requirements} if requirements else None
    for t in model.traces:
        if t.component_id not in ids:
            violations.append(
                Violation(
                    level="L1",
                    rule="trace-endpoints-declared",
                    message=(
                        f"Trace {t.requirement_id} -> {t.component_id} references "
                        f"undeclared component '{t.component_id}'."
                    ),
                    elements=[t.component_id],
                    counterexample=(
                        f"Trace points at '{t.component_id}' which is not a declared component."
                    ),
                )
            )
        if req_ids is not None and t.requirement_id not in req_ids:
            violations.append(
                Violation(
                    level="L1",
                    rule="trace-endpoints-declared",
                    message=(
                        f"Trace {t.requirement_id} -> {t.component_id} references "
                        f"unknown requirement '{t.requirement_id}' (hallucinated requirement)."
                    ),
                    elements=[t.requirement_id],
                    counterexample=(
                        f"No requirement with id '{t.requirement_id}' exists; "
                        f"valid ids are {sorted(req_ids)}."
                    ),
                )
            )

    g = build_graph(model)
    for c in model.components:
        if (
            g.degree(c.id) == 0
            and c.type != ComponentType.external
            and len(model.components) > 1
        ):
            violations.append(
                Violation(
                    level="L1",
                    rule="no-orphan-components",
                    message=f"Component '{c.id}' is connected to nothing.",
                    elements=[c.id],
                    counterexample=(
                        f"'{c.id}' has no incoming or outgoing connectors; connect it or drop it."
                    ),
                )
            )

    for conn in model.connectors:
        src, tgt = model.component(conn.source), model.component(conn.target)
        if src and tgt and (src.type, tgt.type) in FORBIDDEN_TYPE_PAIRS:
            violations.append(
                Violation(
                    level="L1",
                    rule="valid-type-pairs",
                    message=(
                        f"Connector {conn.source} -> {conn.target}: a {src.type.value} "
                        f"component cannot initiate calls to a {tgt.type.value} component."
                    ),
                    elements=[conn.source, conn.target],
                    counterexample=(
                        f"Reverse the dependency or route it through a service: "
                        f"{src.type.value} '{conn.source}' must not call "
                        f"{tgt.type.value} '{conn.target}'."
                    ),
                )
            )

    return violations
