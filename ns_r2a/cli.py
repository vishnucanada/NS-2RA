"""Typer CLI: `ns-r2a generate <requirements.md> -o out/`."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from . import render
from .l0_generate import generate_architecture
from .l0_normalize import normalize
from .llm import DEFAULT_MODEL, OllamaBackend
from .repair import repair_loop
from .schemas import ArchitectureModel, RequirementSet

app = typer.Typer(add_completion=False, help="Neuro-symbolic requirements-to-architecture.")
console = Console()


@app.command()
def generate(
    requirements_file: Path = typer.Argument(..., exists=True, readable=True),
    out: Path = typer.Option(Path("out"), "--out", "-o", help="Output directory"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Ollama model name"),
    max_repairs: int = typer.Option(3, "--max-repairs", help="Repair rounds before giving up"),
):
    """Generate verified architecture views from a requirements document."""
    backend = OllamaBackend(model=model)
    document = requirements_file.read_text()

    console.print(f"[bold]L0a[/bold] normalizing requirements with [cyan]{model}[/cyan] ...")
    reqs = normalize(document, backend)
    console.print(
        f"      {len(reqs.requirements)} requirements "
        f"({len(reqs.functional_ids())} functional)"
    )

    console.print("[bold]L0b[/bold] generating architecture model ...")
    arch = generate_architecture(reqs, backend)
    console.print(f"      {len(arch.components)} components, {len(arch.connectors)} connectors")

    console.print("[bold]L1+L2[/bold] verifying (graph diagnostics + Z3) ...")

    def on_round(round_number: int, violations):
        console.print(
            f"      round {round_number}: [red]{len(violations)} violation(s)[/red]"
            + ("" if round_number == max_repairs else " -> repairing")
        )
        for v in violations:
            console.print(f"        [dim]{v.level}:{v.rule}[/dim] {v.message}")

    result = repair_loop(arch, reqs, backend, max_repairs=max_repairs, on_round=on_round)

    out.mkdir(parents=True, exist_ok=True)
    (out / "requirements.json").write_text(reqs.model_dump_json(indent=2))
    (out / "architecture.json").write_text(result.model.model_dump_json(indent=2))
    (out / "component.puml").write_text(render.component_view(result.model))
    (out / "layers.puml").write_text(render.layer_view(result.model))
    (out / "report.md").write_text(render.report(result, reqs))

    if result.verified:
        console.print(f"[bold green]VERIFIED[/bold green] — all rules hold. Outputs in {out}/")
    else:
        console.print(
            f"[bold yellow]UNVERIFIED[/bold yellow] — "
            f"{len(result.remaining_violations)} violation(s) remain after "
            f"{max_repairs} repair round(s). See {out}/report.md"
        )
        raise typer.Exit(code=1)


@app.command()
def check(
    architecture_file: Path = typer.Argument(..., exists=True, readable=True),
    requirements_file: Path = typer.Argument(..., exists=True, readable=True),
):
    """Verify an existing architecture.json against requirements.json (no LLM)."""
    arch = ArchitectureModel.model_validate(json.loads(architecture_file.read_text()))
    reqs = RequirementSet.model_validate(json.loads(requirements_file.read_text()))

    from .repair import check_all

    violations = check_all(arch, reqs)
    if not violations:
        console.print("[bold green]VERIFIED[/bold green] — all rules hold.")
        return
    for v in violations:
        console.print(f"[red]{v.level}:{v.rule}[/red] {v.message}")
        if v.counterexample:
            console.print(f"  [dim]{v.counterexample}[/dim]")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
