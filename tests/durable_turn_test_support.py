"""Shared deterministic providers for durable turn application tests."""

import json

from bootstrap.campaign_runtime import CampaignRuntimeFactory
from models.player_intent_analysis import PlayerIntentAnalysis
from services.providers import FakeLLMProvider, LLMProviderError


class CombinedMechanicsFakeProvider(FakeLLMProvider):
    """Wrap a mechanics-only fixture in the strict combined v2 response."""

    def generate(self, prompt: str) -> str:
        if not isinstance(prompt, str):
            raise TypeError("prompt must be a string")
        self.prompts.append(prompt)
        if self.error is not None:
            raise LLMProviderError("Fake LLM provider error") from self.error
        if self.response is None:
            raise ValueError("a fixed mechanics response is required")

        marker = "=== EVIDENCIA ESCRITA POR EL JUGADOR"
        marker_index = prompt.find(marker)
        if marker_index < 0:
            raise ValueError("mechanics prompt is missing player-authored evidence")
        header_end = prompt.find(") ===", marker_index)
        if header_end < 0:
            raise ValueError("mechanics prompt has an invalid evidence section")
        evidence_start = header_end + len(") ===")
        escaped_newline = chr(92) + "n"
        while evidence_start < len(prompt) and (
            prompt[evidence_start].isspace()
            or prompt.startswith(escaped_newline, evidence_start)
        ):
            evidence_start += 2 if prompt.startswith(escaped_newline, evidence_start) else 1
        evidence_end = prompt.find(
            "El contexto completo puede contener",
            evidence_start,
        )
        if evidence_end < 0:
            raise ValueError("mechanics prompt has an unterminated evidence section")
        evidence_text = prompt[evidence_start:evidence_end]
        evidence_text = evidence_text.replace(escaped_newline, " ").strip()
        if not evidence_text:
            raise ValueError("mechanics prompt has empty player-authored evidence")

        analysis = PlayerIntentAnalysis.conservative_legacy(evidence_text)
        # Keep the legacy lexical classifier as a test convenience, but emit
        # the strict current envelope expected by the production turn path.
        intent_payload = analysis.to_dict()
        intent_payload["schema_version"] = 2
        for step in intent_payload["steps"]:
            excerpt = step["source_excerpt"]
            step["action_frame"] = {
                "predicate": excerpt[:120],
                "family": "unknown",
                "arguments": [],
            }
        intent_payload["relation_claims"] = []
        return json.dumps(
            {
                "intent_analysis": intent_payload,
                "mechanics_decision": json.loads(self.response),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


def service_with_fake_models():
    """Return the real durable turn service with deterministic in-memory providers."""
    runtime = CampaignRuntimeFactory().get_runtime(1)
    service = runtime.durable_native_turn_service
    service.resolver.mechanics_adjudicator = None
    proposal_calls = []
    service.resolver.extractor.provider = lambda prompt: (
        proposal_calls.append(prompt) or '{"operations": []}'
    )
    narrative_calls = []
    service.resolver.dm_service.provider.generate = lambda prompt: (
        narrative_calls.append(prompt) or "El personaje observa su entorno."
    )
    return service, proposal_calls, narrative_calls
