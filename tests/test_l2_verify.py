from ns_r2a.l2_verify import verify
from ns_r2a.schemas import Connector, RequirementKind, Trace

from .fakes import (
    make_requirements,
    make_valid_model,
    with_cycle,
    with_layering_violation,
)


def rules(result):
    return {v.rule for v in result.violations}


def test_valid_model_verifies():
    result = verify(make_valid_model(), make_requirements())
    assert result.ok, [v.render() for v in result.violations]


def test_layering_violation_with_counterexample():
    result = verify(with_layering_violation(make_valid_model()), make_requirements())
    assert rules(result) == {"layering"}
    (v,) = result.violations
    assert "event_queue" in v.elements and "notifier" in v.elements
    assert "layer(event_queue)=3" in v.counterexample


def test_cycle_detected_via_unsat_core():
    result = verify(with_cycle(make_valid_model()), make_requirements())
    assert "acyclicity" in rules(result)
    v = next(v for v in result.violations if v.rule == "acyclicity")
    assert set(v.elements) == {"order_service", "notifier"}


def test_uncovered_functional_requirement():
    model = make_valid_model()
    model.traces = [t for t in model.traces if t.requirement_id != "R2"]
    result = verify(model, make_requirements())
    assert rules(result) == {"requirement-coverage"}
    assert result.violations[0].elements == ["R2"]


def test_non_functional_requirements_do_not_need_traces():
    # R3 is non-functional and untraced in the valid model; that's fine.
    result = verify(make_valid_model(), make_requirements())
    assert "requirement-coverage" not in rules(result)


def test_zero_and_multiple_entrypoints():
    model = make_valid_model()
    model.components[0].entrypoint = False
    result = verify(model, make_requirements())
    assert "single-entrypoint" in rules(result)

    model = make_valid_model()
    model.components[1].entrypoint = True
    result = verify(model, make_requirements())
    v = next(v for v in result.violations if v.rule == "single-entrypoint")
    assert set(v.elements) == {"storefront", "order_service"}


def test_interface_not_provided_by_target():
    model = make_valid_model()
    model.connectors.append(
        Connector(source="notifier", target="orders_db", interface="email_store")
    )
    result = verify(model, make_requirements())
    assert rules(result) == {"interface-compatibility"}
    assert "email_store" in result.violations[0].message


def test_multiple_violations_all_reported():
    model = with_layering_violation(with_cycle(make_valid_model()))
    model.traces = []
    result = verify(model, make_requirements())
    reqs = make_requirements()
    functional = [r.id for r in reqs.requirements if r.kind == RequirementKind.functional]
    coverage = [v for v in result.violations if v.rule == "requirement-coverage"]
    assert {v.elements[0] for v in coverage} == set(functional)
    assert "layering" in rules(result)
    assert "acyclicity" in rules(result)
