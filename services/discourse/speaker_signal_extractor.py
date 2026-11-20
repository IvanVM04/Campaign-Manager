"""Evidence-only speaker and speech-predicate signal extraction."""

from __future__ import annotations

import re
from collections.abc import Iterable

from services.discourse.contracts import AttributedNpcUtterance, SpeechPredicateSignal
from services.discourse.surface_mention_extractor import SurfaceMentionExtractor
from services.discourse.speech_predicates import SPEECH_PREDICATE_FORMS


class SpeakerSignalExtractor(SurfaceMentionExtractor):
    """Extract literal speaker/speech signals with strict visibility and ambiguity gates."""

    _SPEECH_VERBS = "|".join(SPEECH_PREDICATE_FORMS)

    @classmethod
    def speech_predicate_signals(
        cls,
        value: str,
        *,
        visible_entities: Iterable[object] = (),
    ) -> tuple[SpeechPredicateSignal, ...]:
        """Detect literal speech cues with a pronoun or unique visible NPC subject.

        A named subject is eligible only when its exact alias belongs to one
        active visible NPC. Quoted spans and ambiguous aliases are ignored.
        """
        if not isinstance(value, str) or not value:
            return ()
        masked = cls._mask_quoted_spans(value)
        verbs = sorted(cls._SPEECH_VERBS.split("|"), key=len, reverse=True)
        verb_pattern = "|".join(re.escape(item) for item in verbs)
        signals: list[SpeechPredicateSignal] = []
        pronoun_pattern = re.compile(
            r"(?<!\w)(?P<subject>ellas|ellos|ella|él|she|he|they)\s+"
            r"(?:(?:me|te|le|les|nos)\s+)?"
            r"(?P<predicate>" + verb_pattern + r")(?!\w)",
            re.IGNORECASE,
        )
        pronoun_spans: set[tuple[int, int]] = set()
        for match in pronoun_pattern.finditer(masked):
            subject = value[match.start("subject"):match.end("subject")]
            predicate = value[match.start("predicate"):match.end("predicate")]
            features = cls.pronoun_agreement(subject)
            if features is None:
                continue
            pronoun_spans.add((match.start("subject"), match.end("subject")))
            signals.append(
                SpeechPredicateSignal(
                    subject=subject,
                    predicate=predicate,
                    subject_start=match.start("subject"),
                    subject_end=match.end("subject"),
                    predicate_start=match.start("predicate"),
                    predicate_end=match.end("predicate"),
                    gender=features[0],
                    number=features[1],
                    subject_kind="pronoun",
                )
            )

        unique_aliases: dict[str, tuple[object, str] | None] = {}
        for identity, _name, aliases in cls._visible_npc_specs(visible_entities):
            for alias in aliases:
                key = cls.normalize(alias)
                if not key:
                    continue
                existing = unique_aliases.get(key)
                if key not in unique_aliases:
                    unique_aliases[key] = (identity, alias)
                elif existing is not None and existing[0] != identity:
                    unique_aliases[key] = None

        for entry in unique_aliases.values():
            if entry is None:
                continue
            _identity, alias = entry
            alias_pattern = re.escape(alias).replace(r"\ ", r"\s+")
            named_pattern = re.compile(
                r"(?<!\w)(?P<subject>" + alias_pattern + r")(?!\w)\s+"
                r"(?:(?:me|te|le|les|nos)\s+)?"
                r"(?P<predicate>" + verb_pattern + r")(?!\w)",
                re.IGNORECASE,
            )
            for match in named_pattern.finditer(masked):
                span = (match.start("subject"), match.end("subject"))
                if any(span[0] < end and start < span[1] for start, end in pronoun_spans):
                    continue
                signals.append(
                    SpeechPredicateSignal(
                        subject=value[span[0]:span[1]],
                        predicate=value[match.start("predicate"):match.end("predicate")],
                        subject_start=span[0],
                        subject_end=span[1],
                        predicate_start=match.start("predicate"),
                        predicate_end=match.end("predicate"),
                        gender="unknown",
                        number="unknown",
                        subject_kind="visible_npc",
                    )
                )
        signals.sort(key=lambda item: (item.subject_start, item.predicate_start))
        return tuple(signals)

    @classmethod
    def _subject_pronoun(cls, value: str) -> str | None:
        """Find a third-person subject pronoun without reading quoted dialogue."""
        match = re.search(
            r"(?<!\w)(?P<pronoun>ellas|ellos|ella|él)\s+[a-záéíóúüñ]+",
            cls._without_quoted_spans(value),
            flags=re.IGNORECASE,
        )
        return match.group("pronoun") if match is not None else None

    @classmethod
    def _visible_npc_specs(
        cls, visible_entities: Iterable[object],
    ) -> tuple[tuple[object, str, tuple[str, ...]], ...]:
        """Return active visible NPC labels without inferring identity from names."""
        result = []
        seen: set[object] = set()
        for index, entity in enumerate(visible_entities):
            entity_id = cls._entity_value(entity, "id")
            entity_type = cls.normalize(
                str(cls._entity_value(entity, "entity_type", ""))
            ).replace("_", "").replace(" ", "")
            name = cls._entity_value(entity, "name", "")
            if (
                not bool(cls._entity_value(entity, "active", False))
                or not ("npc" in entity_type or "nonplayer" in entity_type)
                or not isinstance(name, str) or not name.strip()
            ):
                continue
            identity = entity_id if entity_id is not None else (name.casefold(), index)
            if identity in seen:
                continue
            seen.add(identity)
            raw_aliases = cls._entity_value(entity, "aliases", []) or []
            aliases = raw_aliases if isinstance(raw_aliases, (list, tuple)) else []
            labels = tuple(dict.fromkeys(
                item.strip()
                for item in (name, *aliases)
                if isinstance(item, str) and item.strip()
            ))
            result.append((identity, name.strip(), labels))
        return tuple(result)

    @classmethod
    def _npc_pronoun_hint(
        cls, current_input: str, recent_turns: Iterable[object],
        visible_entities: Iterable[object],
    ) -> str | None:
        """Render explicit historical agreement as a hint, never as player evidence."""
        pronoun = cls._subject_pronoun(current_input)
        if pronoun is None:
            return None
        agreement = cls.pronoun_agreement(pronoun)
        if agreement is None:
            return None
        gender, number = agreement
        candidates: list[tuple[str, int | None]] = []
        for _identity, name, aliases in cls._visible_npc_specs(visible_entities):
            evidence_turn = None
            for turn in recent_turns:
                player_input, _narrative, turn_id = cls._turn_fields(turn)
                if player_input and any(
                    cls.grammatical_features(player_input, alias) == (gender, "singular")
                    for alias in aliases
                ):
                    evidence_turn = turn_id
                    break
            if evidence_turn is not None:
                candidates.append((name, evidence_turn))
        if number == "singular":
            if len(candidates) == 1:
                name, turn_id = candidates[0]
                turn_label = f" en el turno {turn_id}" if turn_id is not None else " en el historial"
                return (
                    f"Concordancia explícita del sujeto «{pronoun}»: un único NPC visible, "
                    f"«{name}», aparece con marca gramatical {gender} singular{turn_label}. "
                    "Es una pista, no evidencia nueva: conserva el pronombre literal y no lo "
                    "sustituyas por el nombre."
                )
            if len(candidates) > 1:
                names = ", ".join(sorted({name for name, _ in candidates})[:4])
                return (
                    f"El sujeto «{pronoun}» tiene concordancia {gender} singular, pero varios "
                    f"NPC visibles encajan ({names}). No elijas uno por el nombre ni inventes "
                    "atribución; mantén el referente sin resolver o pide aclaración."
                )
            return (
                f"El sujeto «{pronoun}» está en tercera persona, pero el historial no aporta "
                "una concordancia NPC única. No lo conviertas automáticamente en una acción "
                "del jugador por el hecho de que el jugador haya escrito el mensaje; clasifica "
                "el evento por su actor gramatical y no inventes un nombre o una identidad."
            )
        if len(candidates) >= 2:
            names = ", ".join(sorted({name for name, _ in candidates})[:5])
            return (
                f"El sujeto plural «{pronoun}» puede referirse a un grupo de al menos dos NPC "
                f"con marcas explícitas {gender} singular en el historial ({names}). "
                "Consérvalo como grupo: no lo reduzcas a una persona ni emitas esos nombres "
                "como menciones literales del jugador."
            )
        return (
            f"El sujeto plural «{pronoun}» no tiene un grupo NPC único demostrado por concordancia. "
            "No lo reduzcas a una persona ni lo conviertas automáticamente en una acción del jugador."
        )

    @classmethod
    def _ambiguous_npc_speaker_aliases(
        cls, recent_turns: Iterable[object], visible_entities: Iterable[object],
    ) -> tuple[str, ...]:
        """Find historical quote labels shared by multiple visible active NPCs."""
        owners: dict[str, tuple[str, set[object]]] = {}
        for identity, _name, aliases in cls._visible_npc_specs(visible_entities):
            for alias in aliases:
                key = cls.normalize(alias)
                if not key:
                    continue
                owners.setdefault(key, (alias, set()))[1].add(identity)
        narratives = [
            cls.normalize(cls._turn_fields(turn)[1])
            for turn in recent_turns if cls._turn_fields(turn)[1]
        ]
        ambiguous = []
        for key, (label, identities) in owners.items():
            if len(identities) < 2:
                continue
            pattern = r"(?<!\w)" + re.escape(key).replace(r"\ ", r"\s+") + r"(?!\w)"
            if any(re.search(pattern, narrative) for narrative in narratives):
                ambiguous.append(label)
        return tuple(sorted(set(ambiguous), key=str.casefold))

    @classmethod
    def _current_speech_predicates(cls, value: str) -> tuple[str, ...]:
        """Find non-negated lexical speech predicates in current player evidence."""
        normalized = cls.normalize(cls._without_quoted_spans(value))
        verbs = sorted(
            {cls.normalize(item) for item in SPEECH_PREDICATE_FORMS},
            key=len, reverse=True,
        )
        pattern = r"(?<!\w)(?:" + "|".join(re.escape(item) for item in verbs) + r")(?!\w)"
        found = []
        for match in re.finditer(pattern, normalized):
            immediate_prefix = normalized[max(0, match.start() - 40):match.start()]
            if re.search(
                r"\b(?:no|nunca|jamas|never|not)"
                r"(?:\s+(?:le|les|lo|la|los|las|se|me|te)){0,2}\s*$",
                immediate_prefix,
            ):
                continue
            if match.group(0) not in found:
                found.append(match.group(0))
            if len(found) == 2:
                break
        return tuple(found)

    @classmethod
    def extract_npc_utterances(
        cls,
        narrative: str,
        turn_id: int | None,
        visible_entities: Iterable[object],
    ) -> tuple[AttributedNpcUtterance, ...]:
        """Extract quoted speech only when a unique visible active NPC labels it."""
        if not isinstance(narrative, str) or not narrative.strip():
            return ()
        aliases: dict[str, tuple[object, str, int] | None] = {}
        for entity in visible_entities:
            entity_id = cls._entity_value(entity, "id")
            raw_type = str(cls._entity_value(entity, "entity_type", ""))
            entity_type = cls.normalize(raw_type).replace("_", "").replace(" ", "")
            if (
                isinstance(entity_id, bool) or not isinstance(entity_id, int)
                or entity_id < 1
                or not bool(cls._entity_value(entity, "active", False))
                or not ("npc" in entity_type or "nonplayer" in entity_type)
            ):
                continue
            name = cls._entity_value(entity, "name", "")
            aliases_value = cls._entity_value(entity, "aliases", []) or []
            aliases_list = aliases_value if isinstance(aliases_value, (list, tuple)) else []
            for alias in [name, *aliases_list]:
                if not isinstance(alias, str) or not alias.strip() or len(alias) > 120:
                    continue
                key = cls.normalize(alias)
                if not key:
                    continue
                existing = aliases.get(key)
                if key not in aliases:
                    aliases[key] = (entity, alias.strip(), entity_id)
                elif existing is not None and existing[2] != entity_id:
                    aliases[key] = None

        results: dict[tuple[int, str], AttributedNpcUtterance] = {}
        for value in aliases.values():
            if value is None:
                continue
            entity, alias, speaker_entity_id = value
            escaped = re.escape(alias)
            patterns = (
                re.compile(
                    r"(?<!\w)(?P<speaker>" + escaped + r")(?!\w)"
                    r"(?:\s+(?:(?:me|te|le|les|nos)\s+)?(?:" + cls._SPEECH_VERBS + r"))?\s*[:：]\s*"
                    r"[«“\\\"](?P<utterance>[^»”\\\"]{1,600})[»”\\\"]",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"[«“\\\"](?P<utterance>[^»”\\\"]{1,600})[»”\\\"]"
                    r"\s*[—-]\s*(?:" + cls._SPEECH_VERBS + r")\s+"
                    r"(?P<speaker>" + escaped + r")(?!\w)",
                    re.IGNORECASE,
                ),
            )
            for pattern in patterns:
                for match in pattern.finditer(narrative):
                    utterance = match.group("utterance").strip()
                    if not utterance:
                        continue
                    item = AttributedNpcUtterance(
                        turn_id=turn_id,
                        speaker_entity_id=speaker_entity_id,
                        speaker_name=str(cls._entity_value(entity, "name", alias))[:120],
                        excerpt=match.group(0).strip()[:1200],
                        utterance=utterance[:600],
                    )
                    results.setdefault(
                        (item.speaker_entity_id, cls.normalize(item.utterance)),
                        item,
                    )
        return tuple(results.values())
