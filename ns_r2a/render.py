"""Deterministic rendering: ArchitectureModel -> PlantUML views + report.

PlantUML is generated from the validated model, never by the LLM, so the
diagrams are syntactically correct by construction and always consistent
with what was verified.
"""

from __future__ import annotations

from .repair import PipelineResult
from .schemas import ArchitectureModel, ComponentType, Layer, RequirementSet

_TYPE_STEREOTYPE = {
    ComponentType.ui: "<<ui>>",
    ComponentType.service: "<<service>>",
    ComponentType.database: "<<database>>",
    ComponentType.queue: "<<queue>>",
    ComponentType.external: "<<external>>",
}


def _puml_component(cid: str, name: str, ctype: ComponentType, entrypoint: bool) -> str:
    stereo = _TYPE_STEREOTYPE[ctype]
    if ctype == ComponentType.database:
        return f'database "{name}" as {cid} {stereo}'
    if ctype == ComponentType.queue:
        return f'queue "{name}" as {cid} {stereo}'
    if ctype == ComponentType.external:
        return f'actor "{name}" as {cid} {stereo}'
    label = f"{name} (entry)" if entrypoint else name
    return f'component "{label}" as {cid} {stereo}'


def component_view(model: ArchitectureModel) -> str:
    lines = ["@startuml", f"title {model.system_name} — component view", "skinparam linetype ortho"]
    for c in model.components:
        lines.append(_puml_component(c.id, c.name, c.type, c.entrypoint))
    for c in model.components:
        for iface in c.provides:
            lines.append(f'interface "{iface}" as {c.id}__{_safe(iface)}')
            lines.append(f"{c.id} -up- {c.id}__{_safe(iface)}")
    for conn in model.connectors:
        label = " : ".join(x for x in (conn.protocol, conn.interface) if x)
        arrow = f"{conn.source} --> {conn.target}"
        lines.append(f"{arrow} : {label}" if label else arrow)
    lines.append("@enduml")
    return "\n".join(lines) + "\n"


def layer_view(model: ArchitectureModel) -> str:
    lines = ["@startuml", f"title {model.system_name} — layer view"]
    for layer in Layer:
        members = [c for c in model.components if c.layer == layer]
        if not members:
            continue
        lines.append(f'package "{layer.value}" {{')
        for c in members:
            lines.append("  " + _puml_component(c.id, c.name, c.type, c.entrypoint))
        lines.append("}")
    for conn in model.connectors:
        lines.append(f"{conn.source} --> {conn.target}")
    lines.append("@enduml")
    return "\n".join(lines) + "\n"


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name)


def report(result: PipelineResult, requirements: RequirementSet) -> str:
    model = result.model
    status = "VERIFIED ✅" if result.verified else "UNVERIFIED ⚠️"
    lines = [
        f"# Verification report: {model.system_name}",
        "",
        f"**Status: {status}**",
        "",
        f"- Components: {len(model.components)}",
        f"- Connectors: {len(model.connectors)}",
        f"- Requirements: {len(requirements.requirements)} "
        f"({len(requirements.functional_ids())} functional)",
        f"- Repair rounds used: {max(len(result.rounds) - (0 if result.verified else 1), 0)}"
        if result.rounds
        else "- Repair rounds used: 0 (correct on first generation)",
        "",
        "## Rules checked",
        "",
    ]
    failed_now = {v.rule for v in result.remaining_violations}
    for rule in result.rules_checked:
        mark = "❌" if rule in failed_now else "✅"
        lines.append(f"- {mark} `{rule}`")

    if result.rounds:
        lines += ["", "## Repair history", ""]
        for rnd in result.rounds:
            lines.append(f"### Round {rnd.round_number}: {len(rnd.violations)} violation(s)")
            lines.append("")
            for v in rnd.violations:
                lines.append(f"- `{v.level}:{v.rule}` — {v.message}")
                if v.counterexample:
                    lines.append(f"  - counterexample: {v.counterexample}")
            lines.append("")

    if not result.verified:
        lines += [
            "## Remaining violations",
            "",
            "The repair budget was exhausted; the outputs below reflect the last",
            "candidate and **must not be trusted** for the failed rules above.",
            "",
        ]

    lines += ["", "## Requirement traceability", ""]
    traced = {t.requirement_id: [] for t in model.traces}
    for t in model.traces:
        traced[t.requirement_id].append(t.component_id)
    for r in requirements.requirements:
        targets = ", ".join(f"`{c}`" for c in traced.get(r.id, [])) or "*untraced*"
        lines.append(f"- **{r.id}** ({r.kind.value}): {r.text} → {targets}")

    return "\n".join(lines) + "\n"
