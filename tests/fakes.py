"""Deterministic test doubles: a fake LLM backend and canned models."""

from __future__ import annotations

from ns_r2a.schemas import (
    ArchitectureModel,
    Component,
    ComponentType,
    Connector,
    Layer,
    Requirement,
    RequirementKind,
    RequirementSet,
    Trace,
)


class FakeLLMBackend:
    """Returns queued responses in order; records the prompts it saw."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def generate(self, system, prompt, schema):
        self.calls.append((system, prompt))
        if not self.responses:
            raise AssertionError("FakeLLMBackend ran out of queued responses")
        response = self.responses.pop(0)
        assert isinstance(response, schema), f"queued {type(response)} but asked for {schema}"
        return response


def make_requirements() -> RequirementSet:
    return RequirementSet(
        title="Order System",
        requirements=[
            Requirement(
                id="R1",
                text="The system shall let customers place orders.",
                kind=RequirementKind.functional,
                actors=["customer"],
                entities=["order"],
            ),
            Requirement(
                id="R2",
                text="The system shall send a confirmation email asynchronously.",
                kind=RequirementKind.functional,
                actors=["customer"],
                entities=["email"],
            ),
            Requirement(
                id="R3",
                text="Catalog searches shall respond within 500 ms (p95).",
                kind=RequirementKind.non_functional,
                entities=["catalog"],
            ),
        ],
    )


def make_valid_model() -> ArchitectureModel:
    return ArchitectureModel(
        system_name="Order System",
        components=[
            Component(
                id="storefront",
                name="Web Storefront",
                layer=Layer.presentation,
                type=ComponentType.ui,
                entrypoint=True,
                requires=["order_api"],
            ),
            Component(
                id="order_service",
                name="Order Service",
                layer=Layer.application,
                type=ComponentType.service,
                provides=["order_api"],
                requires=["order_store", "events"],
            ),
            Component(
                id="notifier",
                name="Notification Service",
                layer=Layer.application,
                type=ComponentType.service,
                requires=["events"],
            ),
            Component(
                id="orders_db",
                name="Orders DB",
                layer=Layer.infrastructure,
                type=ComponentType.database,
                provides=["order_store"],
            ),
            Component(
                id="event_queue",
                name="Event Queue",
                layer=Layer.infrastructure,
                type=ComponentType.queue,
                provides=["events"],
            ),
        ],
        connectors=[
            Connector(source="storefront", target="order_service", interface="order_api", protocol="HTTP"),
            Connector(source="order_service", target="orders_db", interface="order_store", protocol="SQL"),
            Connector(source="order_service", target="event_queue", interface="events", protocol="AMQP"),
            Connector(source="notifier", target="event_queue", interface="events", protocol="AMQP"),
        ],
        traces=[
            Trace(requirement_id="R1", component_id="order_service"),
            Trace(requirement_id="R2", component_id="notifier"),
        ],
    )


def with_hallucinated_edge(model: ArchitectureModel) -> ArchitectureModel:
    broken = model.model_copy(deep=True)
    broken.connectors.append(
        Connector(source="order_service", target="payment_gateway", protocol="HTTP")
    )
    return broken


def with_layering_violation(model: ArchitectureModel) -> ArchitectureModel:
    # notifier (application) -> storefront (presentation) points upward but
    # closes no cycle, so it violates exactly one rule.
    broken = model.model_copy(deep=True)
    broken.connectors.append(
        Connector(source="notifier", target="storefront", interface="", protocol="HTTP")
    )
    return broken


def with_cycle(model: ArchitectureModel) -> ArchitectureModel:
    broken = model.model_copy(deep=True)
    broken.connectors.append(
        Connector(source="notifier", target="order_service", interface="order_api")
    )
    broken.connectors.append(
        Connector(source="order_service", target="notifier", interface="")
    )
    return broken
