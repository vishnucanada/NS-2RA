from ns_r2a.l1_graph import check_structure
from ns_r2a.schemas import Component, ComponentType, Connector, Layer, Trace

from .fakes import make_requirements, make_valid_model, with_hallucinated_edge


def rules(violations):
    return {v.rule for v in violations}


def test_valid_model_passes():
    assert check_structure(make_valid_model(), make_requirements()) == []


def test_hallucinated_edge_detected():
    violations = check_structure(with_hallucinated_edge(make_valid_model()), make_requirements())
    assert rules(violations) == {"edge-endpoints-declared"}
    (v,) = violations
    assert "payment_gateway" in v.counterexample


def test_trace_to_unknown_component_and_requirement():
    model = make_valid_model()
    model.traces.append(Trace(requirement_id="R1", component_id="ghost"))
    model.traces.append(Trace(requirement_id="R99", component_id="notifier"))
    violations = check_structure(model, make_requirements())
    assert rules(violations) == {"trace-endpoints-declared"}
    assert len(violations) == 2


def test_duplicate_component_ids():
    model = make_valid_model()
    model.components.append(model.components[0].model_copy(deep=True))
    violations = check_structure(model, make_requirements())
    assert "unique-component-ids" in rules(violations)


def test_orphan_component():
    model = make_valid_model()
    model.components.append(
        Component(id="lonely", name="Lonely", layer=Layer.domain, type=ComponentType.service)
    )
    violations = check_structure(model, make_requirements())
    assert rules(violations) == {"no-orphan-components"}


def test_self_loop():
    model = make_valid_model()
    model.connectors.append(Connector(source="notifier", target="notifier"))
    violations = check_structure(model, make_requirements())
    assert "no-self-loops" in rules(violations)


def test_database_initiating_call_is_invalid():
    model = make_valid_model()
    model.connectors.append(Connector(source="orders_db", target="order_service"))
    violations = check_structure(model, make_requirements())
    assert "valid-type-pairs" in rules(violations)
