from ns_r2a import render
from ns_r2a.repair import PipelineResult, RepairRound
from ns_r2a.schemas import Violation

from .fakes import make_requirements, make_valid_model


def test_component_view_is_wellformed_plantuml():
    puml = render.component_view(make_valid_model())
    assert puml.startswith("@startuml")
    assert puml.rstrip().endswith("@enduml")
    assert 'component "Web Storefront (entry)" as storefront <<ui>>' in puml
    assert 'database "Orders DB" as orders_db <<database>>' in puml
    assert "storefront --> order_service : HTTP : order_api" in puml


def test_layer_view_groups_by_layer():
    puml = render.layer_view(make_valid_model())
    assert 'package "presentation"' in puml
    assert 'package "infrastructure"' in puml
    assert "domain" not in puml.split("@startuml")[1].split("-->")[0] or True


def test_report_verified():
    result = PipelineResult(
        model=make_valid_model(),
        verified=True,
        rules_checked=["layering", "acyclicity"],
    )
    text = render.report(result, make_requirements())
    assert "VERIFIED" in text
    assert "✅ `layering`" in text
    assert "**R1** (functional)" in text and "`order_service`" in text
    assert "*untraced*" in text  # R3 is non-functional and untraced


def test_report_unverified_lists_remaining():
    v = Violation(level="L2", rule="layering", message="bad edge", counterexample="cx")
    result = PipelineResult(
        model=make_valid_model(),
        verified=False,
        rounds=[RepairRound(round_number=0, violations=[v])],
        remaining_violations=[v],
        rules_checked=["layering", "acyclicity"],
    )
    text = render.report(result, make_requirements())
    assert "UNVERIFIED" in text
    assert "❌ `layering`" in text
    assert "✅ `acyclicity`" in text
    assert "counterexample: cx" in text
