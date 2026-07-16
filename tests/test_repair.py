from ns_r2a.repair import check_all, repair_loop

from .fakes import (
    FakeLLMBackend,
    make_requirements,
    make_valid_model,
    with_hallucinated_edge,
    with_layering_violation,
)


def test_valid_model_needs_no_repair():
    backend = FakeLLMBackend([])
    result = repair_loop(make_valid_model(), make_requirements(), backend)
    assert result.verified
    assert result.rounds == []
    assert backend.calls == []


def test_l1_violations_block_l2():
    # A hallucinated edge must surface alone; Z3 rules run only once L1 is clean.
    violations = check_all(with_hallucinated_edge(make_valid_model()), make_requirements())
    assert {v.level for v in violations} == {"L1"}


def test_repair_fixes_model_in_one_round():
    reqs = make_requirements()
    backend = FakeLLMBackend([make_valid_model()])
    result = repair_loop(with_layering_violation(make_valid_model()), reqs, backend)
    assert result.verified
    assert len(result.rounds) == 1
    assert result.rounds[0].violations[0].rule == "layering"
    # The repair prompt must carry the counterexample to the model.
    _, prompt = backend.calls[0]
    assert "layering" in prompt and "event_queue" in prompt


def test_budget_exhaustion_reports_unverified():
    reqs = make_requirements()
    broken = with_layering_violation(make_valid_model())
    backend = FakeLLMBackend([broken.model_copy(deep=True), broken.model_copy(deep=True)])
    result = repair_loop(broken, reqs, backend, max_repairs=2)
    assert not result.verified
    assert len(result.rounds) == 3  # initial + 2 failed repairs
    assert result.remaining_violations
