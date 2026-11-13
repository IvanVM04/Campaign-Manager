"""Safe, evidence-bound corrections for an uncommitted player-intent draft.

This model deliberately has no persistence or world-mutation capability. A
correction can only be applied while its durable resolution is still pending.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from enum import Enum

from models.player_intent_analysis import PlayerIntentAnalysis
from models.semantic_frames import (
    SemanticArgument,
    SemanticArgumentRole,
    SemanticMention,
)


class PendingCorrectionSlot(str, Enum):
    TARGET_MENTION = "target_mention"
    ACTION_ARGUMENT = "action_argument"
    RELATION_SUBJECT = "relation_subject"
    RELATION_OBJECT = "relation_object"


@dataclass(frozen=True, slots=True)
class PendingIntentCorrection:
    """An explicit player correction to one slot of one pending intent step."""

    step_index: int
    slot: PendingCorrectionSlot
    previous_value: str
    replacement: SemanticMention
    source_excerpt: str
    argument_role: SemanticArgumentRole | None = None
    relation_claim_index: int | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.step_index, bool)
            or not isinstance(self.step_index, int)
            or self.step_index < 0
        ):
            raise ValueError("step_index must be a non-negative integer")
        if not isinstance(self.slot, PendingCorrectionSlot):
            raise TypeError("slot must be a PendingCorrectionSlot")
        _validate_text(self.previous_value, "previous_value", 120)
        _validate_text(self.source_excerpt, "source_excerpt", 300)
        if not isinstance(self.replacement, SemanticMention):
            raise TypeError("replacement must be a SemanticMention")
        if self.slot is PendingCorrectionSlot.ACTION_ARGUMENT:
            if not isinstance(self.argument_role, SemanticArgumentRole):
                raise ValueError("action-argument correction requires an argument_role")
        elif self.argument_role is not None:
            raise ValueError("argument_role is only valid for action-argument corrections")
        if self.slot in {
            PendingCorrectionSlot.RELATION_SUBJECT,
            PendingCorrectionSlot.RELATION_OBJECT,
        }:
            if (
                isinstance(self.relation_claim_index, bool)
                or not isinstance(self.relation_claim_index, int)
                or self.relation_claim_index < 0
            ):
                raise ValueError("relation correction requires a non-negative claim index")
        elif self.relation_claim_index is not None:
            raise ValueError("relation_claim_index is only valid for relation corrections")

    def apply(
        self,
        analysis: PlayerIntentAnalysis,
        *,
        player_evidence_text: str,
        resolution_pending: bool,
        committed: bool,
    ) -> PlayerIntentAnalysis:
        """Return a corrected copy, refusing committed or weakly grounded edits."""
        if not isinstance(analysis, PlayerIntentAnalysis):
            raise TypeError("analysis must be a PlayerIntentAnalysis")
        if not isinstance(player_evidence_text, str) or not player_evidence_text.strip():
            raise ValueError("player_evidence_text must not be empty")
        if not isinstance(resolution_pending, bool) or not isinstance(committed, bool):
            raise TypeError("pending and committed flags must be booleans")
        if not resolution_pending or committed:
            raise ValueError("only an uncommitted pending resolution may be corrected")
        if self.step_index >= len(analysis.steps):
            raise ValueError("correction references a missing intent step")
        if not _contains_literal(player_evidence_text, self.source_excerpt):
            raise ValueError("correction excerpt is not literal player evidence")
        if not _contains_literal(self.source_excerpt, self.replacement.text):
            raise ValueError("replacement mention is not grounded in correction evidence")
        if self.previous_value.casefold() == self.replacement.text.casefold():
            raise ValueError("correction must change the targeted value")

        steps = list(analysis.steps)
        step = steps[self.step_index]
        if self.slot is PendingCorrectionSlot.TARGET_MENTION:
            matches = [
                index for index, value in enumerate(step.target_mentions)
                if value.casefold() == self.previous_value.casefold()
            ]
            if len(matches) != 1:
                raise ValueError("target correction must identify exactly one existing mention")
            targets = list(step.target_mentions)
            if any(value.casefold() == self.replacement.text.casefold() for value in targets):
                raise ValueError("replacement target is already present")
            targets[matches[0]] = self.replacement.text
            corrected_frame = step.action_frame
            if corrected_frame is not None:
                corrected_arguments = tuple(
                    replace(argument, mention=self.replacement)
                    if argument.mention.text.casefold() == self.previous_value.casefold()
                    else argument
                    for argument in corrected_frame.arguments
                )
                corrected_frame = replace(
                    corrected_frame,
                    arguments=corrected_arguments,
                )
            corrected_claims = list(analysis.relation_claims)
            for index, claim in enumerate(corrected_claims):
                if claim.step_index != self.step_index:
                    continue
                changes = {}
                if claim.subject.text.casefold() == self.previous_value.casefold():
                    changes["subject"] = self.replacement
                if claim.object.text.casefold() == self.previous_value.casefold():
                    changes["object"] = self.replacement
                if changes:
                    corrected_claims[index] = replace(claim, **changes)
            steps[self.step_index] = replace(
                step,
                target_mentions=tuple(targets),
                action_frame=corrected_frame,
            )
            analysis = replace(analysis, relation_claims=tuple(corrected_claims))
        elif self.slot is PendingCorrectionSlot.ACTION_ARGUMENT:
            frame = step.action_frame
            if frame is None:
                raise ValueError("action-argument correction requires a semantic action frame")
            matches = [
                index for index, argument in enumerate(frame.arguments)
                if argument.role is self.argument_role
                and argument.mention.text.casefold() == self.previous_value.casefold()
            ]
            if len(matches) != 1:
                raise ValueError("argument correction must identify exactly one role/value slot")
            arguments = list(frame.arguments)
            arguments[matches[0]] = SemanticArgument(
                role=self.argument_role,
                mention=self.replacement,
            )
            corrected_frame = replace(frame, arguments=tuple(arguments))
            targets = tuple(
                self.replacement.text if value.casefold() == self.previous_value.casefold() else value
                for value in step.target_mentions
            )
            steps[self.step_index] = replace(
                step,
                action_frame=corrected_frame,
                target_mentions=targets,
            )
        else:
            claims = list(analysis.relation_claims)
            if self.relation_claim_index is None or self.relation_claim_index >= len(claims):
                raise ValueError("relation correction references a missing claim")
            claim = claims[self.relation_claim_index]
            if claim.step_index != self.step_index:
                raise ValueError("relation correction must target a claim in the same step")
            field_name = (
                "subject"
                if self.slot is PendingCorrectionSlot.RELATION_SUBJECT
                else "object"
            )
            current = getattr(claim, field_name)
            if current.text.casefold() != self.previous_value.casefold():
                raise ValueError("relation correction does not match the pending endpoint")
            claims[self.relation_claim_index] = replace(
                claim,
                **{field_name: self.replacement},
            )
            return replace(
                analysis,
                steps=tuple(steps),
                relation_claims=tuple(claims),
            )
        return replace(analysis, steps=tuple(steps))


def _validate_text(value: str, field_name: str, maximum: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field_name} must contain 1-{maximum} characters")


def _contains_literal(source: str, fragment: str) -> bool:
    def normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value.casefold())
        plain = "".join(
            character
            for character in decomposed
            if not unicodedata.combining(character)
        )
        return " ".join(re.findall(r"[a-z0-9]+", plain))

    normalized_fragment = normalize(fragment)
    return bool(normalized_fragment) and (
        f" {normalized_fragment} " in f" {normalize(source)} "
    )
