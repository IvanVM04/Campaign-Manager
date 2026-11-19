"""Lazy CPU-only Stanza adapter used only by the optional NLP pilot."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from time import perf_counter
from typing import Any

from services.nlp_pilot.contracts import ParserDocument, ParserSentence, ParserWord


class NlpPilotDependencyError(RuntimeError):
    """Raised when an optional parser dependency or model is unavailable."""


class NlpPilotContractError(ValueError):
    """Raised when a parser returns invalid offsets or dependency structure."""


class StanzaParserAdapter:
    """Map a preinstalled Spanish Stanza pipeline into typed, bounded hints.

    The adapter never downloads models. Install the optional dependency and
    explicitly download the selected models before constructing it.
    """

    ADAPTER_NAME = "stanza"
    DEFAULT_PROCESSORS = "tokenize,mwt,pos,lemma,depparse"
    MAX_TEXT_CHARS = 20_000
    MAX_SENTENCES = 32
    MAX_WORDS = 512

    def __init__(
        self,
        *,
        pipeline: Any | None = None,
        model_dir: str | Path | None = None,
        language: str = "es",
        model_package: str = "default",
    ) -> None:
        if not isinstance(language, str) or not language.strip():
            raise ValueError("language must be a non-empty string")
        if not isinstance(model_package, str) or not model_package.strip():
            raise ValueError("model_package must be a non-empty string")
        self.language = language.strip()
        self.model_package = model_package.strip()
        self.processors = self.DEFAULT_PROCESSORS
        self.adapter_name = self.ADAPTER_NAME
        self._pipeline = pipeline
        self._library_version = "injected"

        if self._pipeline is None:
            try:
                import stanza  # type: ignore[import-not-found]
            except ImportError as exc:
                raise NlpPilotDependencyError(
                    "Stanza is optional. Install it with: pip install --group nlp-pilot"
                ) from exc

            kwargs: dict[str, Any] = {
                "lang": self.language,
                "processors": self.DEFAULT_PROCESSORS,
                "package": self.model_package,
                "use_gpu": False,
                "download_method": None,
                "verbose": False,
            }
            if model_dir is not None:
                kwargs["model_dir"] = str(Path(model_dir).expanduser())
            try:
                self._pipeline = stanza.Pipeline(**kwargs)
            except Exception as exc:
                raise NlpPilotDependencyError(
                    "Stanza models are missing or could not be loaded; download them explicitly first"
                ) from exc
            self._library_version = str(getattr(stanza, "__version__", "unknown"))

    @property
    def library_version(self) -> str:
        return self._library_version

    @staticmethod
    def _features(raw: Any) -> tuple[tuple[str, str], ...]:
        if raw is None or raw == "":
            return ()
        if not isinstance(raw, str):
            raise NlpPilotContractError("Stanza morphology must be text")
        parsed: list[tuple[str, str]] = []
        for item in raw.split("|"):
            key, separator, value = item.partition("=")
            if separator and key.strip() and value.strip():
                parsed.append((key.strip(), value.strip()))
        return tuple(sorted(parsed))

    def parse(self, text: str) -> ParserDocument:
        """Parse one current-message string and return validated source spans."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if not text.strip():
            raise ValueError("text must not be empty")
        if len(text) > self.MAX_TEXT_CHARS:
            raise ValueError(f"text must not exceed {self.MAX_TEXT_CHARS} characters")

        pipeline = self._pipeline
        if pipeline is None:
            raise NlpPilotDependencyError("Stanza pipeline is not configured")

        started = perf_counter()
        try:
            parsed = pipeline(text)
        except Exception as exc:
            raise NlpPilotDependencyError("Stanza failed to parse the message") from exc

        raw_sentences = getattr(parsed, "sentences", None)
        if not isinstance(raw_sentences, Sequence):
            raise NlpPilotContractError("Stanza document must expose a sentence sequence")
        if len(raw_sentences) > self.MAX_SENTENCES:
            raise NlpPilotContractError("Stanza sentence count exceeds the pilot bound")

        sentences: list[ParserSentence] = []
        total_words = 0
        previous_token_end = 0
        for sentence_index, raw_sentence in enumerate(raw_sentences):
            raw_tokens = getattr(raw_sentence, "tokens", None)
            if not isinstance(raw_tokens, Sequence):
                raise NlpPilotContractError("Stanza sentence must expose a token sequence")

            token_rows: list[tuple[int, int, list[Any]]] = []
            flat_words: list[Any] = []
            word_token_indices: list[int] = []
            for token_index, token in enumerate(raw_tokens):
                start = getattr(token, "start_char", None)
                end = getattr(token, "end_char", None)
                if (
                    isinstance(start, bool)
                    or not isinstance(start, int)
                    or isinstance(end, bool)
                    or not isinstance(end, int)
                    or not previous_token_end <= start < end <= len(text)
                ):
                    raise NlpPilotContractError("Stanza returned an invalid or overlapping source offset")
                token_text = getattr(token, "text", None)
                if not isinstance(token_text, str) or text[start:end] != token_text:
                    raise NlpPilotContractError(
                        "Stanza source offset does not exactly match its token surface"
                    )
                previous_token_end = end
                raw_words = getattr(token, "words", None)
                if not isinstance(raw_words, Sequence) or not raw_words:
                    raise NlpPilotContractError("Stanza token must contain at least one word")
                token_rows.append((start, end, list(raw_words)))
                for word in raw_words:
                    flat_words.append(word)
                    word_token_indices.append(token_index)

            total_words += len(flat_words)
            if total_words > self.MAX_WORDS:
                raise NlpPilotContractError("Stanza word count exceeds the pilot bound")

            id_to_index: dict[int, int] = {}
            for word_index, raw_word in enumerate(flat_words):
                raw_id = getattr(raw_word, "id", None)
                if isinstance(raw_id, bool) or not isinstance(raw_id, int) or raw_id < 1:
                    raise NlpPilotContractError("Stanza word IDs must be positive integers")
                if raw_id in id_to_index:
                    raise NlpPilotContractError("Stanza word IDs must be unique within a sentence")
                id_to_index[raw_id] = word_index

            start_by_token = [row[0] for row in token_rows]
            end_by_token = [row[1] for row in token_rows]
            words: list[ParserWord] = []
            for word_index, raw_word in enumerate(flat_words):
                token_index = word_token_indices[word_index]
                head = getattr(raw_word, "head", None)
                if isinstance(head, bool) or not isinstance(head, int) or head < 0:
                    raise NlpPilotContractError("Stanza dependency head must be a non-negative integer")
                if head != 0 and head not in id_to_index:
                    raise NlpPilotContractError("Stanza dependency head is outside its sentence")
                head_index = None if head == 0 else id_to_index[head]
                lemma = getattr(raw_word, "lemma", None)
                upos = getattr(raw_word, "upos", None)
                xpos = getattr(raw_word, "xpos", None)
                dependency = getattr(raw_word, "deprel", None)
                for value, name in (
                    (lemma, "lemma"),
                    (upos, "upos"),
                    (xpos, "xpos"),
                    (dependency, "deprel"),
                ):
                    if value is not None and not isinstance(value, str):
                        raise NlpPilotContractError(f"Stanza {name} must be text or None")
                words.append(
                    ParserWord(
                        sentence_index=sentence_index,
                        token_index=token_index,
                        word_index=word_index,
                        source_start=start_by_token[token_index],
                        source_end=end_by_token[token_index],
                        lemma=lemma,
                        upos=upos,
                        xpos=xpos,
                        dependency=dependency,
                        head_word_index=head_index,
                        morphology=self._features(getattr(raw_word, "feats", None)),
                    )
                )
            sentences.append(
                ParserSentence(sentence_index=sentence_index, words=tuple(words))
            )

        return ParserDocument(
            adapter_name=self.ADAPTER_NAME,
            language=self.language,
            model_package=self.model_package,
            library_version=self._library_version,
            elapsed_ms=(perf_counter() - started) * 1000,
            sentences=tuple(sentences),
        )
