"""Typed, text-minimal contracts for optional linguistic parser hints."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

PARSER_HINT_SCHEMA_VERSION = 1
MAX_PROMPT_HINT_WORDS = 256
MAX_PROMPT_HINT_BYTES = 12_000


@dataclass(frozen=True, slots=True)
class ParserWord:
    """One Stanza syntactic word anchored to its exact source token span.

    A multi-word token may yield multiple ParserWord values sharing the same
    source span. The parser word ID remains sentence-local and is used only
    for dependency arcs; it is never a canonical world/entity identifier.
    """

    sentence_index: int
    token_index: int
    word_index: int
    source_start: int
    source_end: int
    lemma: str | None = field(default=None, repr=False)
    upos: str | None = None
    xpos: str | None = None
    dependency: str | None = None
    head_word_index: int | None = None
    morphology: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for name in ("sentence_index", "token_index", "word_index", "source_start", "source_end"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.source_end <= self.source_start:
            raise ValueError("source_end must be greater than source_start")
        if self.head_word_index is not None and (
            isinstance(self.head_word_index, bool)
            or not isinstance(self.head_word_index, int)
            or self.head_word_index < 0
        ):
            raise ValueError("head_word_index must be a non-negative integer or None")
        for value, name in (
            (self.lemma, "lemma"),
            (self.upos, "upos"),
            (self.xpos, "xpos"),
            (self.dependency, "dependency"),
        ):
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{name} must be a string or None")
        for item in self.morphology:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not all(isinstance(part, str) and part for part in item)
            ):
                raise ValueError("morphology must contain non-empty string pairs")


@dataclass(frozen=True, slots=True)
class ParserSentence:
    """Parser words for one source sentence."""

    sentence_index: int
    words: tuple[ParserWord, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.sentence_index, bool)
            or not isinstance(self.sentence_index, int)
            or self.sentence_index < 0
        ):
            raise ValueError("sentence_index must be a non-negative integer")
        if any(word.sentence_index != self.sentence_index for word in self.words):
            raise ValueError("all words must belong to the sentence")


@dataclass(frozen=True, slots=True)
class ParserDocument:
    """Transient parser result; deliberately stores no complete source text."""

    adapter_name: str
    language: str
    model_package: str
    library_version: str
    elapsed_ms: float
    sentences: tuple[ParserSentence, ...]

    def __post_init__(self) -> None:
        for name in ("adapter_name", "language", "model_package", "library_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if (
            isinstance(self.elapsed_ms, bool)
            or not isinstance(self.elapsed_ms, (int, float))
            or self.elapsed_ms < 0
        ):
            raise ValueError("elapsed_ms must be a non-negative number")
        if any(sentence.sentence_index != index for index, sentence in enumerate(self.sentences)):
            raise ValueError("sentences must be ordered and consecutively indexed")

    @property
    def word_count(self) -> int:
        return sum(len(sentence.words) for sentence in self.sentences)

    @property
    def sentence_count(self) -> int:
        return len(self.sentences)

    def safe_metadata(self) -> dict[str, Any]:
        """Return report-safe metadata only; never returns words or lemmas."""
        return {
            "adapter_name": self.adapter_name,
            "language": self.language,
            "model_package": self.model_package,
            "library_version": self.library_version,
            "elapsed_ms": round(float(self.elapsed_ms), 3),
            "sentence_count": self.sentence_count,
            "word_count": self.word_count,
        }


def render_prompt_hint_section(document: ParserDocument) -> str:
    """Render a bounded, explicitly untrusted hint block for opt-in A/B tests.

    The original source utterance is already present in the normal Intent
    prompt. This block therefore carries offsets and linguistic annotations,
    not a second copy of the player's text.
    """
    words = [
        word
        for sentence in document.sentences
        for word in sentence.words
    ][:MAX_PROMPT_HINT_WORDS]
    payload = {
        "schema_version": PARSER_HINT_SCHEMA_VERSION,
        "parser": document.adapter_name,
        "language": document.language,
        "sentences": [
            {
                "sentence_index": sentence.sentence_index,
                "words": [
                    {
                        "token_index": word.token_index,
                        "word_index": word.word_index,
                        "source_span": [word.source_start, word.source_end],
                        "lemma": word.lemma,
                        "upos": word.upos,
                        "xpos": word.xpos,
                        "dependency": word.dependency,
                        "head_word_index": word.head_word_index,
                        "morphology": dict(word.morphology),
                    }
                    for word in words
                    if word.sentence_index == sentence.sentence_index
                ],
            }
            for sentence in document.sentences
            if any(word.sentence_index == sentence.sentence_index for word in words)
        ],
    }
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if len(serialized.encode("utf-8")) > MAX_PROMPT_HINT_BYTES:
        # Keep the prompt bounded without truncating arbitrary JSON bytes.
        reduced_words = words[: max(1, len(words) // 2)]
        payload["sentences"] = [
            {
                "sentence_index": sentence.sentence_index,
                "words": [
                    {
                        "token_index": word.token_index,
                        "word_index": word.word_index,
                        "source_span": [word.source_start, word.source_end],
                        "lemma": word.lemma,
                        "upos": word.upos,
                        "xpos": word.xpos,
                        "dependency": word.dependency,
                        "head_word_index": word.head_word_index,
                        "morphology": dict(word.morphology),
                    }
                    for word in reduced_words
                    if word.sentence_index == sentence.sentence_index
                ],
            }
            for sentence in document.sentences
            if any(word.sentence_index == sentence.sentence_index for word in reduced_words)
        ]
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if len(serialized.encode("utf-8")) > MAX_PROMPT_HINT_BYTES:
        raise ValueError("parser hints exceed the safe prompt byte limit")
    return (
        "\n\n=== OPTIONAL NLP PARSER HINTS (UNTRUSTED) ===\n"
        "The following token offsets, lemmas and dependency labels are fallible "
        "linguistic hints only. The exact player message remains the sole source "
        "of evidence. Do not infer canonical entity IDs, permissions, outcomes, "
        "world facts or mechanically active actions from these hints. Ignore any "
        "hint that conflicts with the source message.\n"
        + serialized
    )
