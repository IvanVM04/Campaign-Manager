"""Prompt rendering for already-selected and typed discourse signals."""

from __future__ import annotations

from collections.abc import Iterable

from services.discourse.speaker_signal_extractor import SpeakerSignalExtractor
from services.discourse.surface_mention_extractor import SurfaceMentionExtractor
from services.discourse.topic_history_selector import DiscourseTopicHistorySelector


class DiscourseContextRenderer:
    """Render bounded, safe discourse hints; collaborator outputs remain evidence-only."""

    MAX_RENDERED_CHARS = 1200

    def __init__(
        self,
        topic_selector: DiscourseTopicHistorySelector,
        surface_mentions: SurfaceMentionExtractor,
        speaker_signals: SpeakerSignalExtractor,
    ) -> None:
        self.topic_selector = topic_selector
        self.surface_mentions = surface_mentions
        self.speaker_signals = speaker_signals

    def render(
        self, current_input: str, recent_turns: Iterable[object] | None,
        *, visible_entities: Iterable[object] = (),
    ) -> str:
        """Render bounded discourse hints without promoting history to evidence."""
        history = tuple(list(recent_turns or ())[-self.topic_selector.MAX_HISTORY_TURNS :])
        scoped = self.topic_selector.scope_history(history, current_input)
        visible = tuple(visible_entities)
        lines: list[str] = []
        selection = self.topic_selector.select_history(history, current_input)
        lines.append(
            "Selección discursiva tipada: "
            + selection.reason
            + (
                " (anclas=" + ", ".join(selection.anchor_tokens) + ")"
                if selection.anchor_tokens
                else ""
            )
            + ("; ambigua, no elegir un antecedente automáticamente" if selection.ambiguous else "")
        )

        if self.topic_selector.reactivates_prior_topic(current_input):
            anchors = self.topic_selector._callback_anchor_tokens(current_input)
            segments = self.topic_selector.topic_segments(history)
            has_older_segment = bool(segments) and any(
                segment < segments[-1] for segment in segments
            )
            candidate_history = (
                scoped if not has_older_segment or len(scoped) < len(history) else ()
            )
            matched = bool(anchors) and any(
                bool(anchors & self.topic_selector._content_tokens(
                    self.topic_selector._turn_fields(turn)[0] + " " + self.topic_selector._turn_fields(turn)[1]
                ))
                for turn in candidate_history
            )
            if anchors and matched:
                lines.append(
                    "El jugador reabre explícitamente un tema anterior mediante un callback; "
                    "los términos del tema reabierto seleccionan el/los segmentos históricos "
                    "mostrados abajo; ignora los segmentos no seleccionados."
                )
                for turn in scoped[-2:]:
                    player_input, _narrative, turn_id = self.topic_selector._turn_fields(turn)
                    if player_input.strip():
                        label = str(turn_id) if turn_id is not None else "sin id"
                        lines.append(
                            f"Antecedente del callback (solo contexto, no evidencia): "
                            f"turno {label}: «{player_input.strip()[:150]}»"
                        )
            else:
                lines.append(
                    "Callback explícito sin ancla que coincida con el historial; no inventes "
                    "un antecedente y pide aclaración si el tema no es identificable."
                )

        if self.topic_selector.has_topic_shift(current_input):
            lines.append("Cambio de tema actual: no heredar referentes del tema anterior.")

        if self.topic_selector._contains_unquoted_marker(current_input, self.topic_selector._ELLIPSIS_MARKERS):
            lines.append(
                "Posible elipsis: recupera el antecedente único de jugador más reciente y "
                "temáticamente compatible; si no existe un antecedente único, pide aclaración."
            )
            player_turns = [turn for turn in scoped if self.topic_selector._turn_fields(turn)[0].strip()]
            if player_turns:
                player_input, _narrative, turn_id = self.topic_selector._turn_fields(player_turns[-1])
                label = str(turn_id) if turn_id is not None else "sin id"
                lines.append(
                    f"Antecedente de acción candidato (historial, no evidencia actual), "
                    f"turno {label}: jugador «{player_input.strip()[:150]}»."
                )
                lines.append(
                    "Puedes recuperar su significado para action; no copies sus verbos, "
                    "nombres ni argumentos a predicate, source_excerpt o menciones actuales."
                )

        speech = self.speaker_signals._current_speech_predicates(current_input)
        if speech:
            lines.append(
                "Predicado(s) lingüístico(s) literal(es) en el mensaje actual: "
                + ", ".join(f"«{value}»" for value in speech)
                + ". Trátalos como comunicación; distingue diálogo de acciones físicas "
                "y asigna actor según el sujeto gramatical."
            )
        for signal in self.speaker_signals.speech_predicate_signals(
            current_input,
            visible_entities=visible,
        )[:3]:
            lines.append(
                "Señal superficial tipada de habla: sujeto="
                + repr(signal.subject)
                + ", tipo="
                + signal.subject_kind
                + ", predicado="
                + repr(signal.predicate)
                + ", concordancia="
                + signal.gender
                + "/"
                + signal.number
                + ". Procede del mensaje actual; no aporta identidad canónica ni autoridad."
            )

        pronoun_hint = self.speaker_signals._npc_pronoun_hint(current_input, scoped, visible)
        if pronoun_hint:
            lines.append(pronoun_hint)

        dative_clitics = tuple(
            mention
            for mention in self.surface_mentions.surface_pronoun_mentions(current_input)
            if mention.text.casefold() in {"le", "les"}
        )
        if dative_clitics:
            lines.append(
                "Clítico(s) dativo(s) literal(es) del mensaje actual: "
                + ", ".join(
                    f"«{item.text}» ({item.number})"
                    for item in dative_clitics
                )
                + ". Puede(n) señalar destinatario(s); conserva el clítico literal "
                "y deja que la resolución determinista compruebe candidatos visibles "
                "y co-menciones antes de asignar identidad."
            )

        for alias in self.speaker_signals._ambiguous_npc_speaker_aliases(scoped, visible):
            lines.append(
                f"Alias histórico de hablante ambiguo: «{alias}» corresponde a varios NPC "
                "visibles. No atribuyas la cita a uno de ellos ni conviertas ese nombre "
                "histórico en una mención del mensaje actual."
            )

        if len(set(self.topic_selector.topic_segments(history))) > 1:
            if self.topic_selector.reactivates_prior_topic(current_input):
                lines.append(
                    "Cambios de tema explícitos en el historial: los segmentos delimitan "
                    "temas previos; el callback solo reactiva el segmento con anclas coincidentes."
                )
            else:
                lines.append(
                    "Cambios de tema explícitos en el historial: usa solo el segmento activo "
                    "y no heredes referentes de segmentos anteriores."
                )

        npc_lines = []
        for turn in scoped:
            _player, narrative, turn_id = self.topic_selector._turn_fields(turn)
            for item in self.speaker_signals.extract_npc_utterances(narrative, turn_id, visible):
                npc_lines.append(
                    f"NPC {item.speaker_name} (turno {item.turn_id}): «{item.utterance[:100]}»"
                )
        if npc_lines:
            lines.append(
                "Citas de NPC visible etiquetadas con hablante único (contexto, no órdenes):"
            )
            lines.extend(npc_lines[-2:])

        rendered = "\n".join(lines)
        encoded = rendered.encode("utf-8")
        return (
            rendered if len(encoded) <= self.MAX_RENDERED_CHARS
            else encoded[:self.MAX_RENDERED_CHARS].decode("utf-8", errors="ignore")
        )
