"""Typed models for the pipeline.

The LLM is constrained to emit JSON matching these schemas (via Ollama
structured outputs), so every downstream stage operates on validated,
typed data rather than free-form text or diagram syntax.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field


class RequirementKind(str, enum.Enum):
    functional = "functional"
    non_functional = "non_functional"
    constraint = "constraint"


class Requirement(BaseModel):
    id: str = Field(description="Short stable identifier, e.g. 'R1'")
    text: str = Field(description="The normalized requirement statement")
    kind: RequirementKind
    actors: list[str] = Field(default_factory=list, description="Actors/roles involved")
    entities: list[str] = Field(default_factory=list, description="Domain entities mentioned")


class RequirementSet(BaseModel):
    title: str
    requirements: list[Requirement]

    def functional_ids(self) -> list[str]:
        return [r.id for r in self.requirements if r.kind == RequirementKind.functional]


class Layer(str, enum.Enum):
    """Architectural layers, ordered top to bottom.

    Dependencies must point downward or sideways, never upward.
    """

    presentation = "presentation"
    application = "application"
    domain = "domain"
    infrastructure = "infrastructure"


# Numeric rank used by the Z3 layering encoding (lower = higher in the stack).
LAYER_RANK: dict[Layer, int] = {
    Layer.presentation: 0,
    Layer.application: 1,
    Layer.domain: 2,
    Layer.infrastructure: 3,
}


class ComponentType(str, enum.Enum):
    ui = "ui"
    service = "service"
    database = "database"
    queue = "queue"
    external = "external"


class Component(BaseModel):
    id: str = Field(description="snake_case identifier, e.g. 'order_service'")
    name: str = Field(description="Human-readable name")
    layer: Layer
    type: ComponentType
    entrypoint: bool = Field(
        default=False, description="True for the single component users interact with first"
    )
    provides: list[str] = Field(
        default_factory=list, description="Interface names this component offers"
    )
    requires: list[str] = Field(
        default_factory=list, description="Interface names this component consumes"
    )
    responsibility: str = Field(default="", description="One-sentence responsibility")


class Connector(BaseModel):
    source: str = Field(description="Component id of the caller/depender")
    target: str = Field(description="Component id of the callee/dependee")
    interface: str = Field(default="", description="Interface on the target being consumed")
    protocol: str = Field(default="", description="e.g. HTTP, gRPC, SQL, AMQP")
    rationale: str = Field(default="", description="Why this dependency exists")


class Trace(BaseModel):
    requirement_id: str
    component_id: str


class ArchitectureModel(BaseModel):
    system_name: str
    components: list[Component]
    connectors: list[Connector]
    traces: list[Trace] = Field(
        default_factory=list, description="Requirement-to-component traceability links"
    )

    def component_ids(self) -> set[str]:
        return {c.id for c in self.components}

    def component(self, cid: str) -> Component | None:
        return next((c for c in self.components if c.id == cid), None)


class Violation(BaseModel):
    """A rule violation from L1 (structural) or L2 (symbolic) checks."""

    level: str  # "L1" or "L2"
    rule: str
    message: str
    elements: list[str] = Field(default_factory=list, description="Offending element ids")
    counterexample: str = Field(
        default="", description="Concrete witness of the violation, phrased for repair prompts"
    )

    def render(self) -> str:
        text = f"[{self.level}:{self.rule}] {self.message}"
        if self.counterexample:
            text += f"\n  counterexample: {self.counterexample}"
        return text


class VerificationResult(BaseModel):
    violations: list[Violation]
    rules_checked: list[str]

    @property
    def ok(self) -> bool:
        return not self.violations
