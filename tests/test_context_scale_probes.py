from __future__ import annotations

from services.context import ContextBuilder

from tests.context_scale_test_support import (
    build_large_campaign_world,
    projection_fingerprint,
)


def test_large_campaign_selection_is_bounded_and_reports_category_diagnostics():
    world = build_large_campaign_world(entity_count=900)
    before = repr(world)

    projection = ContextBuilder().build_proposal_context(
        world,
        "guardia del puerto",
        max_estimated_tokens=9000,
        mandatory_entity_ids=(1, 2),
    )

    diagnostics = projection.diagnostics
    available = dict(diagnostics.available_counts)
    candidates = dict(diagnostics.candidate_counts)
    selected = dict(diagnostics.selected_counts)

    assert available["entities"] == 902
    assert candidates["entities"] >= 900
    assert selected["entities"] < candidates["entities"]
    assert diagnostics.selected_records < diagnostics.available_records
    assert diagnostics.excluded_records > 0
    assert diagnostics.estimated_tokens <= diagnostics.budget_tokens
    assert {1, 2}.issubset(projection.world.entities)
    assert "secret-smuggling-route" not in projection.world.events
    assert repr(world) == before


def test_large_campaign_ranking_and_projection_are_stable_across_insertion_order():
    builder = ContextBuilder()
    first_world = build_large_campaign_world(
        entity_count=700,
        reverse_insertion=False,
    )
    second_world = build_large_campaign_world(
        entity_count=700,
        reverse_insertion=True,
    )

    first = builder.build_proposal_context(
        first_world,
        "guardia del puerto",
        max_estimated_tokens=6500,
        mandatory_entity_ids=(1, 2),
    )
    second = builder.build_proposal_context(
        second_world,
        "guardia del puerto",
        max_estimated_tokens=6500,
        mandatory_entity_ids=(1, 2),
    )

    assert projection_fingerprint(first) == projection_fingerprint(second)


def test_context_budget_growth_admits_more_optional_records_without_losing_mandatory_facts():
    world = build_large_campaign_world(entity_count=600)
    builder = ContextBuilder()

    constrained = builder.build_proposal_context(
        world,
        "guardia del puerto",
        max_estimated_tokens=2400,
        mandatory_entity_ids=(1, 2),
    )
    expanded = builder.build_proposal_context(
        world,
        "guardia del puerto",
        max_estimated_tokens=9000,
        mandatory_entity_ids=(1, 2),
    )

    constrained_ids = set(constrained.world.entities)
    expanded_ids = set(expanded.world.entities)

    assert {1, 2}.issubset(constrained_ids)
    assert {1, 2}.issubset(expanded_ids)
    assert constrained_ids.issubset(expanded_ids)
    assert len(expanded_ids) > len(constrained_ids)
    assert constrained.diagnostics.estimated_tokens <= 2400
    assert expanded.diagnostics.estimated_tokens <= 9000


def test_large_campaign_dependency_bundles_keep_related_records_and_filter_secret_events():
    world = build_large_campaign_world(entity_count=600)
    before = repr(world)

    projection = ContextBuilder().build_proposal_context(
        world,
        "Fungoso",
        max_estimated_tokens=5000,
        mandatory_entity_ids=(1, 2),
    )

    selected = projection.world
    assert {1, 2, 3}.issubset(selected.entities)
    assert set(selected.relations) == {
        "player-location",
        "player-guard",
        "guard-location",
    }
    assert set(selected.item_instances) == {100}
    assert set(selected.items) == {10}
    assert set(selected.resource_balances) == {200}
    assert set(selected.resources) == {20}
    assert set(selected.events) == {"public-guard-shift"}
    assert "secret-smuggling-route" not in selected.events
    assert repr(world) == before
