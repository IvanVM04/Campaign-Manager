"""Offline contracts for the optional Stanza parser pilot."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from services.nlp_pilot.contracts import ParserDocument, ParserSentence, ParserWord, render_prompt_hint_section
from services.nlp_pilot.probes import (
    BinaryProbeCounts,
    NlpPilotProbeLedger,
    expected_utterance_probes,
    lexical_utterance_probes,
    parser_utterance_probes,
)
from services.nlp_pilot.stanza_adapter import NlpPilotContractError, StanzaParserAdapter
from tests.nlp_pilot_support import ParserHintingProvider


def _word(
    *,
    identifier: int,
    lemma: str,
    upos: str,
    dependency: str,
    head: int,
    feats: str | None = None,
):
    return SimpleNamespace(
        id=identifier,
        lemma=lemma,
        upos=upos,
        xpos=None,
        deprel=dependency,
        head=head,
        feats=feats,
    )


def _token(start: int, end: int, *words):
    return SimpleNamespace(start_char=start, end_char=end, words=list(words))


def _document(*tokens):
    return SimpleNamespace(
        sentences=[SimpleNamespace(tokens=list(tokens))]
    )


def test_stanza_adapter_maps_offsets_and_dependency_heads_without_source_text():
    parsed = _document(
        _token(0, 5, _word(identifier=1, lemma="abrir", upos="VERB", dependency="root", head=0)),
        _token(6, 9,
            _word(identifier=2, lemma="de", upos="ADP", dependency="case", head=4),
            _word(identifier=3, lemma="el", upos="DET", dependency="det", head=4),
        ),
        _token(10, 15, _word(identifier=4, lemma="puerta", upos="NOUN", dependency="obj", head=1, feats="Gender=Fem|Number=Sing")),
    )
    adapter = StanzaParserAdapter(pipeline=lambda _text: parsed)

    result = adapter.parse("Abro del puerta")

    assert result.adapter_name == "stanza"
    assert result.language == "es"
    assert result.word_count == 4
    assert result.sentence_count == 1
    assert result.sentences[0].words[0].source_start == 0
    assert result.sentences[0].words[0].source_end == 5
    assert result.sentences[0].words[1].source_start == 6
    assert result.sentences[0].words[2].source_start == 6
    assert result.sentences[0].words[3].head_word_index == 0
    assert result.sentences[0].words[3].morphology == (
        ("Gender", "Fem"),
        ("Number", "Sing"),
    )
    assert not hasattr(result, "source_text")


def test_stanza_adapter_rejects_invalid_or_fuzzy_source_offsets():
    parsed = _document(
        _token(-1, 3, _word(identifier=1, lemma="abrir", upos="VERB", dependency="root", head=0))
    )
    adapter = StanzaParserAdapter(pipeline=lambda _text: parsed)

    with pytest.raises(NlpPilotContractError, match="invalid source offset"):
        adapter.parse("Abro")


def test_stanza_adapter_rejects_dependency_heads_outside_sentence():
    parsed = _document(
        _token(0, 4, _word(identifier=1, lemma="abrir", upos="VERB", dependency="root", head=9))
    )
    adapter = StanzaParserAdapter(pipeline=lambda _text: parsed)

    with pytest.raises(NlpPilotContractError, match="outside its sentence"):
        adapter.parse("Abro")


def test_stanza_adapter_rejects_duplicate_word_ids():
    parsed = _document(
        _token(0, 4, _word(identifier=1, lemma="abrir", upos="VERB", dependency="root", head=0)),
        _token(5, 9, _word(identifier=1, lemma="puerta", upos="NOUN", dependency="obj", head=1)),
    )
    adapter = StanzaParserAdapter(pipeline=lambda _text: parsed)

    with pytest.raises(NlpPilotContractError, match="unique within a sentence"):
        adapter.parse("Abro puerta")


@pytest.mark.parametrize("text", ["", "   "])
def test_stanza_adapter_rejects_empty_messages(text):
    adapter = StanzaParserAdapter(pipeline=lambda _text: _document())

    with pytest.raises(ValueError, match="must not be empty"):
        adapter.parse(text)


def test_stanza_adapter_rejects_oversized_messages_before_calling_parser():
    called = False

    def pipeline(_text):
        nonlocal called
        called = True
        return _document()

    adapter = StanzaParserAdapter(pipeline=pipeline)

    with pytest.raises(ValueError, match="must not exceed"):
        adapter.parse("x" * (adapter.MAX_TEXT_CHARS + 1))
    assert not called


def test_parser_document_safe_metadata_never_includes_lemmas():
    result = ParserDocument(
        adapter_name="stanza",
        language="es",
        model_package="default",
        library_version="1.15.1",
        elapsed_ms=3.2,
        sentences=(
            ParserSentence(
                sentence_index=0,
                words=(
                    ParserWord(
                        sentence_index=0,
                        token_index=0,
                        word_index=0,
                        source_start=0,
                        source_end=4,
                        lemma="abrir",
                        upos="VERB",
                        dependency="root",
                    ),
                ),
            ),
        ),
    )

    assert result.safe_metadata() == {
        "adapter_name": "stanza",
        "language": "es",
        "model_package": "default",
        "library_version": "1.15.1",
        "elapsed_ms": 3.2,
        "sentence_count": 1,
        "word_count": 1,
    }
    assert "abrir" not in json.dumps(result.safe_metadata())


def test_prompt_hint_section_contains_structure_but_not_utterance_copy():
    result = ParserDocument(
        adapter_name="stanza",
        language="es",
        model_package="default",
        library_version="1.15.1",
        elapsed_ms=1,
        sentences=(
            ParserSentence(
                sentence_index=0,
                words=(
                    ParserWord(
                        sentence_index=0,
                        token_index=0,
                        word_index=0,
                        source_start=0,
                        source_end=5,
                        lemma="abrir",
                        upos="VERB",
                        dependency="root",
                    ),
                ),
            ),
        ),
    )

    section = render_prompt_hint_section(result)

    assert "UNTRUSTED" in section
    assert '"source_span":[0,5]' in section
    assert '"lemma":"abrir"' in section
    assert "Abro la puerta" not in section
    assert "canonical entity IDs" in section


def test_prompt_hint_section_is_bounded():
    words = tuple(
        ParserWord(
            sentence_index=0,
            token_index=index,
            word_index=index,
            source_start=index,
            source_end=index + 1,
            lemma="x" * 100,
            upos="NOUN",
            dependency="dep",
            head_word_index=None,
        )
        for index in range(256)
    )
    result = ParserDocument(
        adapter_name="stanza",
        language="es",
        model_package="default",
        library_version="1.15.1",
        elapsed_ms=0,
        sentences=(ParserSentence(sentence_index=0, words=words),),
    )

    with pytest.raises(ValueError, match="safe prompt byte limit"):
        render_prompt_hint_section(result)


def test_gold_probe_extraction_only_scores_annotated_fields():
    scenario = {
        "expected": {
            "category": "action",
            "active_step_index": 0,
            "step": {"polarity": "negative", "modality": "conditional"},
        }
    }
    assert expected_utterance_probes(scenario) == {
        "negation": True,
        "conditional": True,
    }
    assert expected_utterance_probes({"expected": {"category": "question"}}) == {
        "negation": None,
        "conditional": None,
    }


def test_lexical_and_parser_probes_are_only_binary_cue_candidates():
    assert lexical_utterance_probes("No consigo abrir la puerta si llueve.") == {
        "negation": True,
        "conditional": True,
    }
    result = ParserDocument(
        adapter_name="stanza",
        language="es",
        model_package="default",
        library_version="1.15.1",
        elapsed_ms=0,
        sentences=(
            ParserSentence(
                sentence_index=0,
                words=(
                    ParserWord(0, 0, 0, 0, 2, lemma="no", upos="PART", dependency="advmod"),
                    ParserWord(0, 1, 1, 3, 10, lemma="conseguir", upos="VERB", dependency="root"),
                    ParserWord(0, 2, 2, 11, 13, lemma="si", upos="SCONJ", dependency="mark"),
                ),
            ),
        ),
    )
    assert parser_utterance_probes(result) == {
        "negation": True,
        "conditional": True,
    }


def test_binary_probe_metrics_keep_zero_denominators_unmeasured():
    counts = BinaryProbeCounts()
    counts.record(expected=True, predicted=False)
    counts.record(expected=False, predicted=True)

    assert counts.summary() == {
        "sample_count": 2,
        "true_positive": 0,
        "false_positive": 1,
        "false_negative": 1,
        "true_negative": 0,
        "gold_positive_denominator": 1,
        "predicted_positive_denominator": 1,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
    }
    assert BinaryProbeCounts().summary()["f1"] is None


def test_probe_ledger_does_not_retain_scenario_text_or_unannotated_gold():
    ledger = NlpPilotProbeLedger()
    ledger.record(
        family="held_out:action_attempt",
        expected={"negation": None, "conditional": None},
        lexical={"negation": False, "conditional": False},
        parser={"negation": False, "conditional": True},
    )
    rendered = json.dumps(ledger.summary())

    assert "held_out:action_attempt" in rendered
    assert "unmeasured_cases" in rendered
    assert "utterance" not in rendered
    assert "conditional" in rendered


def test_parser_hint_provider_appends_untrusted_hints_and_preserves_schema():
    class FakeProvider:
        model = "fake-model"
        timeout = 10
        think = False

        def __init__(self):
            self.prompt = None
            self.schema = None

        def generate(self, prompt):
            self.prompt = prompt
            return "plain"

        def generate_structured(self, prompt, *, schema):
            self.prompt = prompt
            self.schema = schema
            return '{"ok":true}'

    inner = FakeProvider()
    wrapper = ParserHintingProvider(inner)  # type: ignore[arg-type]
    wrapper.set_parser_hints(
        ParserDocument(
            adapter_name="stanza",
            language="es",
            model_package="default",
            library_version="1.15.1",
            elapsed_ms=0,
            sentences=(
                ParserSentence(
                    sentence_index=0,
                    words=(
                        ParserWord(0, 0, 0, 0, 4, lemma="abrir", upos="VERB", dependency="root"),
                    ),
                ),
            ),
        )
    )
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

    result = wrapper.generate_structured("source prompt", schema=schema)

    assert result == '{"ok":true}'
    assert inner.schema == schema
    assert inner.prompt.startswith("source prompt")
    assert "OPTIONAL NLP PARSER HINTS (UNTRUSTED)" in inner.prompt
    assert wrapper.model == "fake-model"
    assert wrapper.timeout == 10
    assert wrapper.think is False
    assert wrapper.hint_bytes > 0


def test_parser_hint_provider_can_clear_hints_without_changing_prompt():
    class FakeProvider:
        def generate(self, prompt):
            return prompt

        def generate_structured(self, prompt, *, schema):
            return prompt

    wrapper = ParserHintingProvider(FakeProvider())  # type: ignore[arg-type]
    wrapper.set_parser_hints(None)

    assert wrapper.generate_structured("unchanged", schema={}) == "unchanged"
    assert wrapper.hint_bytes == 0
