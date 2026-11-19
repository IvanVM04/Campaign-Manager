"""Direct contract tests for typed conversation-reference evidence and ranking."""

from types import SimpleNamespace

from models.discourse_evidence import (
    CandidateRankingStatus,
    ConversationReferenceMention,
    DiscourseCandidate,
    DiscourseEvidence,
    DiscourseEvidenceBundle,
    DiscourseMentionOrigin,
    DiscourseSource,
    DiscourseSpeaker,
    EntityDiscourseEvidence,
)
from models.entity import Entity
from models.semantic_frames import SemanticObjectKind
from models.world_state import WorldState
from services.context.conversation_reference_evidence import (
    ConversationReferenceEvidenceExtractor,
)
from services.context.conversation_reference_ranker import (
    ConversationReferenceCandidateRanker,
)


def _turn(turn_id: int, player_input: str, narrative: str = ""):
    return SimpleNamespace(
        id=turn_id,
        player_input=player_input,
        narrative=narrative,
    )


def test_evidence_extractor_preserves_player_provenance_offsets_and_visibility():
    mara = Entity(id=1, name="Mara", entity_type="npc")
    inactive = Entity(
        id=2,
        name="Bram",
        entity_type="npc",
        active=False,
    )
    world = WorldState(entities={1: mara, 2: inactive})
    mention = ConversationReferenceMention(
        text="Le",
        step_index=0,
        kind_hint=SemanticObjectKind.CHARACTER,
        origins=(DiscourseMentionOrigin.SURFACE_PRONOUN,),
        start_offset=0,
        end_offset=2,
    )

    bundle = ConversationReferenceEvidenceExtractor().extract(
        world,
        [_turn(14, "Hablo con Mara sobre el mapa.")],
        current_input="Le pregunto por la llave.",
        mentions=(mention,),
    )

    assert bundle.mentions == (mention,)
    assert bundle.selection_reason == "active_topic_segment"
    assert bundle.selected_turn_count == 1
    assert bundle.selected_turn_ids == (14,)
    assert bundle.selection_ambiguous is False
    assert [item.entity_id for item in bundle.entity_evidence] == [1]

    evidence = bundle.evidence_for(1)
    assert len(evidence) == 1
    assert evidence[0].source is DiscourseSource.PLAYER_INPUT
    assert evidence[0].speaker is DiscourseSpeaker.PLAYER
    assert evidence[0].turn_id == 14
    assert evidence[0].mention == "Mara"
    assert evidence[0].start_offset is not None
    assert evidence[0].excerpt[
        evidence[0].start_offset:evidence[0].end_offset
    ] == "Mara"
    assert bundle.evidence_for(2) == ()


def test_evidence_offsets_do_not_point_inside_a_longer_word():
    entity = Entity(id=3, name="Art", entity_type="npc")
    excerpt = "A cart blocks the road before ART arrives."
    bundle = ConversationReferenceEvidenceExtractor().extract(
        WorldState(entities={3: entity}),
        [_turn(23, excerpt)],
        current_input="¿Dónde está?",
    )

    evidence = bundle.evidence_for(3)
    assert len(evidence) == 1
    span = evidence[0]
    assert span.start_offset is not None
    assert span.end_offset is not None
    assert excerpt[span.start_offset:span.end_offset] == "ART"


def test_evidence_extractor_keeps_narrator_and_explicit_npc_speech_separate():
    mara = Entity(id=1, name="Mara", entity_type="npc")
    world = WorldState(entities={1: mara})

    bundle = ConversationReferenceEvidenceExtractor().extract(
        world,
        [_turn(15, "Hablo con Mara.", "Mara dice: «Volveré pronto».")],
        current_input="¿Qué dijo?",
    )

    evidence = bundle.evidence_for(1)
    assert any(
        item.source is DiscourseSource.PLAYER_INPUT
        and item.speaker is DiscourseSpeaker.PLAYER
        for item in evidence
    )
    assert any(
        item.source is DiscourseSource.NARRATIVE
        and item.speaker is DiscourseSpeaker.NARRATOR
        and item.speaker_entity_id is None
        for item in evidence
    )
    attributed = [
        item for item in evidence
        if item.speaker is DiscourseSpeaker.NPC
    ]
    assert len(attributed) == 1
    assert attributed[0].source is DiscourseSource.NARRATIVE
    assert attributed[0].speaker_entity_id == 1
    assert attributed[0].mention == "Mara"


def test_candidate_ranker_exposes_margin_and_abstains_on_a_tie():
    mara = Entity(id=1, name="Mara", entity_type="npc")
    aldric = Entity(id=2, name="Aldric", entity_type="npc")
    excerpt = "Mara y Aldric llegan juntos a la posada."
    evidence = (
        DiscourseEvidence(
            turn_id=16,
            source=DiscourseSource.PLAYER_INPUT,
            speaker=DiscourseSpeaker.PLAYER,
            mention="Mara",
            excerpt=excerpt,
            recency_rank=1,
        ),
    )
    aldric_evidence = (
        DiscourseEvidence(
            turn_id=16,
            source=DiscourseSource.PLAYER_INPUT,
            speaker=DiscourseSpeaker.PLAYER,
            mention="Aldric",
            excerpt=excerpt,
            recency_rank=1,
        ),
    )
    bundle = DiscourseEvidenceBundle(
        mentions=(),
        entity_evidence=(
            EntityDiscourseEvidence(entity_id=1, evidence=evidence),
            EntityDiscourseEvidence(entity_id=2, evidence=aldric_evidence),
        ),
        selection_reason="active_topic_segment",
        selected_turn_count=1,
        selected_turn_ids=(16,),
    )

    ranking = ConversationReferenceCandidateRanker().rank(
        bundle,
        WorldState(entities={1: mara, 2: aldric}),
        mention="Le",
        kind_hint=SemanticObjectKind.CHARACTER,
    )

    assert ranking.status is CandidateRankingStatus.AMBIGUOUS_MARGIN
    assert ranking.selected_candidate is None
    assert ranking.top_score == ranking.runner_up_score
    assert ranking.margin == 0
    assert ranking.abstention_reason == "discourse_candidates_ambiguous"
    assert tuple(item.entity_id for item in ranking.candidates) == (1, 2)


def test_candidate_ranker_reports_no_evidence_without_fabricating_candidates():
    ranking = ConversationReferenceCandidateRanker().rank(
        DiscourseEvidenceBundle(
            mentions=(),
            entity_evidence=(),
            selection_reason="active_topic_segment",
            selected_turn_count=0,
        ),
        WorldState(entities={
            1: Entity(id=1, name="Mara", entity_type="npc"),
        }),
        mention="Ella",
        kind_hint=SemanticObjectKind.CHARACTER,
    )

    assert ranking.status is CandidateRankingStatus.NO_CANDIDATES
    assert ranking.selected_candidate is None
    assert ranking.abstention_reason == "no_visible_antecedent_evidence"


def test_plural_group_builder_rejects_co_mentions_from_different_speakers():
    excerpt = "La guardia Mara y la mercadera Lía esperan junto a la puerta."
    candidates = (
        DiscourseCandidate(
            entity_id=1,
            entity_name="Mara",
            score=100,
            evidence=(DiscourseEvidence(
                turn_id=21,
                source=DiscourseSource.PLAYER_INPUT,
                speaker=DiscourseSpeaker.PLAYER,
                mention="Mara",
                excerpt=excerpt,
                recency_rank=1,
            ),),
            signals=("recency",),
        ),
        DiscourseCandidate(
            entity_id=2,
            entity_name="Lía",
            score=100,
            evidence=(DiscourseEvidence(
                turn_id=21,
                source=DiscourseSource.NARRATIVE,
                speaker=DiscourseSpeaker.NARRATOR,
                mention="Lía",
                excerpt=excerpt,
                recency_rank=1,
            ),),
            signals=("recency",),
        ),
    )

    group, reason = ConversationReferenceCandidateRanker.group_reference_from_candidates(
        "Ellas",
        candidates,
    )

    assert group is None
    assert reason == "plural_group_not_proven"


def test_plural_group_builder_rejects_more_than_eight_members():
    names = (
        "Mara", "Lía", "Nara", "Sara", "Tara",
        "Vera", "Wera", "Yara", "Zara",
    )
    excerpt = " y ".join(f"la guardia {name}" for name in names) + " esperan."
    candidates = tuple(
        DiscourseCandidate(
            entity_id=index,
            entity_name=name,
            score=100,
            evidence=(DiscourseEvidence(
                turn_id=22,
                source=DiscourseSource.PLAYER_INPUT,
                speaker=DiscourseSpeaker.PLAYER,
                mention=name,
                excerpt=excerpt,
                recency_rank=1,
            ),),
            signals=("recency",),
        )
        for index, name in enumerate(names, start=1)
    )

    group, reason = ConversationReferenceCandidateRanker.group_reference_from_candidates(
        "Ellas",
        candidates,
    )

    assert group is None
    assert reason == "plural_group_not_proven"
