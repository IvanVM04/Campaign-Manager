from services.context.context_ranker import ContextRanker


def test_unknown_relation_uses_default_weight():
    ranker = ContextRanker()

    assert (
        ranker.get_relation_relevance(
            "relation_that_does_not_exist"
        )
        ==
        ranker.DEFAULT_RELATION_RELEVANCE
    )


def test_none_relation_uses_default_weight():
    ranker = ContextRanker()

    assert (
        ranker.get_relation_relevance(None)
        ==
        ranker.DEFAULT_RELATION_RELEVANCE
    )


def test_strong_relation_has_higher_relevance_than_weak_relation():
    ranker = ContextRanker()

    assert (
        ranker.get_relation_relevance("friend")
        >
        ranker.get_relation_relevance("knows")
    )


def test_direct_entity_has_higher_score_than_related_entity():
    ranker = ContextRanker()

    direct = {
        "id": 1,
        "name": "Fungoso",
        "_relevance": 1.0,
    }

    related = {
        "id": 2,
        "name": "Aldric",
        "_relevance": 0.7,
    }

    direct_score = ranker.entity_context_score(
        direct,
        "Fungoso",
    )

    related_score = ranker.entity_context_score(
        related,
        "Fungoso",
    )

    assert direct_score > related_score


def test_direct_query_match_gets_bonus():
    ranker = ContextRanker()

    data = {
        "name": "Fungoso",
        "description": "Un aventurero.",
    }

    score = ranker.direct_match_bonus(
        data,
        "fungoso",
    )

    assert score == ranker.DIRECT_MATCH_BONUS


def test_non_matching_candidate_gets_no_bonus():
    ranker = ContextRanker()

    data = {
        "name": "Aldric",
        "description": "Un minero viejo.",
    }

    score = ranker.direct_match_bonus(
        data,
        "fungoso",
    )

    assert score == 0.0


def test_query_matching_is_case_insensitive():
    ranker = ContextRanker()

    data = {
        "name": "Fungoso",
    }

    score = ranker.direct_match_bonus(
        data,
        "fungoso",
    )

    assert score == ranker.DIRECT_MATCH_BONUS


def test_empty_query_keeps_base_score():
    ranker = ContextRanker()

    score = ranker.score_context_candidate(
        "- Fungoso",
        "",
        1.0,
    )

    assert score == 1.0


def test_matching_words_increase_candidate_score():
    ranker = ContextRanker()

    score = ranker.score_context_candidate(
        "- Fungoso (character): aventurero peculiar",
        "fungoso peculiar",
        1.0,
    )

    assert score > 1.0


def test_no_matching_words_keep_base_score():
    ranker = ContextRanker()

    score = ranker.score_context_candidate(
        "- Fungoso",
        "goblin",
        1.0,
    )

    assert score == 1.0

def test_context_ranker_unknown_relation_uses_default_weight():
    ranker = ContextRanker()

    assert (
        ranker.get_relation_relevance(
            "relation_that_does_not_exist"
        )
        == ranker.DEFAULT_RELATION_RELEVANCE
    )

def test_context_ranker_direct_query_match_gets_bonus():
    ranker = ContextRanker()

    data = {
        "name": "Fungoso",
        "description": "Un aventurero.",
    }

    score = ranker.direct_match_bonus(
        data,
        "fungoso",
    )

    assert score == ranker.DIRECT_MATCH_BONUS

def test_context_ranker_query_matching_is_case_insensitive():
    ranker = ContextRanker()

    data = {
        "name": "Fungoso",
    }

    score = ranker.direct_match_bonus(
        data,
        "fungoso",
    )

    assert score == ranker.DIRECT_MATCH_BONUS

def test_context_ranker_strong_relation_has_higher_relevance():
    ranker = ContextRanker()

    assert (
        ranker.get_relation_relevance("friend")
        >
        ranker.get_relation_relevance("knows")
    )


def test_context_ranker_relation_relevance_is_case_insensitive():
    ranker = ContextRanker()

    assert (
        ranker.get_relation_relevance("FRIEND")
        ==
        ranker.get_relation_relevance("friend")
    )

def test_context_ranker_direct_entity_has_higher_score_than_related():
    ranker = ContextRanker()

    direct = {
        "id": 1,
        "name": "Fungoso",
        "_relevance": 1.0,
    }

    related = {
        "id": 2,
        "name": "Aldric",
        "_relevance": 0.7,
    }

    direct_score = ranker.entity_context_score(
        direct,
        "Fungoso",
    )

    related_score = ranker.entity_context_score(
        related,
        "Fungoso",
    )

    assert direct_score > related_score

def test_context_ranker_non_matching_candidate_gets_no_bonus():
    ranker = ContextRanker()

    data = {
        "name": "Aldric",
        "description": "Un minero viejo.",
    }

    score = ranker.direct_match_bonus(
        data,
        "fungoso",
    )

    assert score == 0.0

def test_context_ranker_word_matching_contributes_to_score():
    ranker = ContextRanker()

    text = "- Fungoso (character): aventurero peculiar"

    score = ranker.score_context_candidate(
        text,
        "fungoso peculiar",
        1.0,
    )

    assert score > 1.0

def test_context_ranker_empty_query_keeps_base_score():
    ranker = ContextRanker()

    score = ranker.score_context_candidate(
        "- Fungoso",
        "",
        1.0,
    )

    assert score == 1.0

def test_relation_relevance_prefers_strong_relationships():
    from services.context.context_ranker import ContextRanker

    ranker = ContextRanker()

    assert (
        ranker.get_relation_relevance("friend")
        > ranker.get_relation_relevance("knows")
    )

    assert (
        ranker.get_relation_relevance("enemy")
        > ranker.get_relation_relevance("knows")
    )

def test_relation_relevance_is_case_insensitive():
    from services.context.context_ranker import ContextRanker

    ranker = ContextRanker()

    assert (
        ranker.get_relation_relevance("FRIEND")
        == ranker.get_relation_relevance("friend")
    )

    assert (
        ranker.get_relation_relevance(" KnOwS ")
        == ranker.get_relation_relevance("knows")
    )

def test_unknown_relation_uses_default_relevance():
    from services.context.context_ranker import ContextRanker

    ranker = ContextRanker()

    assert (
        ranker.get_relation_relevance(
            "completely_unknown_relation"
        )
        == ranker.DEFAULT_RELATION_RELEVANCE
    )

def test_entity_context_score_preserves_relation_relevance():
    from services.context.context_ranker import ContextRanker

    ranker = ContextRanker()

    entity = {
        "id": 2,
        "name": "Borin",
        "_relevance": 0.65,
    }

    score = ranker.entity_context_score(
        entity,
        "Aldric",
    )

    assert score == 0.65

def test_entity_context_score_adds_direct_match_bonus():
    from services.context.context_ranker import ContextRanker

    ranker = ContextRanker()

    entity = {
        "id": 1,
        "name": "Aldric",
        "_relevance": 1.0,
    }

    score = ranker.entity_context_score(
        entity,
        "Aldric",
    )

    assert score == (
        1.0
        + ranker.DIRECT_MATCH_BONUS
    )

def test_direct_entity_has_higher_score_than_unrelated_entity():
    from services.context.context_ranker import ContextRanker

    ranker = ContextRanker()

    direct = {
        "id": 1,
        "name": "Aldric",
        "_relevance": 1.0,
    }

    related = {
        "id": 2,
        "name": "Borin",
        "_relevance": 0.65,
    }

    direct_score = ranker.entity_context_score(
        direct,
        "Aldric",
    )

    related_score = ranker.entity_context_score(
        related,
        "Aldric",
    )

    assert direct_score > related_score

def test_score_context_candidate_rewards_matching_words():
    from services.context.context_ranker import ContextRanker

    ranker = ContextRanker()

    base_score = 0.5

    score = ranker.score_context_candidate(
        "Aldric es un mercader de Vorder's Hold.",
        "Aldric",
        base_score,
    )

    assert score == (
        base_score
        + ranker.DIRECT_MATCH_BONUS
    )

def test_score_context_candidate_does_not_change_empty_query():
    from services.context.context_ranker import ContextRanker

    ranker = ContextRanker()

    assert (
        ranker.score_context_candidate(
            "Aldric",
            "",
            0.5,
        )
        == 0.5
    )