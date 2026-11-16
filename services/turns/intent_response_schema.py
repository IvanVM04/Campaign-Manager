"""Ollama JSON Schemas for shared understanding and pending corrections."""

from copy import deepcopy

_MENTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text", "kind_hint"],
    "properties": {
        "text": {
            "type": "string",
            "description": (
                "Copy the exact literal surface mention from the current player message. "
                "Preserve pronouns, demonstratives, inflection and spelling; never replace "
                "a reference with a canonical name inferred from conversation history."
            ),
            "minLength": 1,
            "maxLength": 120,
        },
        "kind_hint": {
            "type": "string",
            "enum": [
                "character", "creature", "location", "item_definition",
                "item_instance", "event", "faction", "resource",
                "world_entity", "unknown",
            ],
        },
    },
}

_ACTION_ARGUMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["role", "mention"],
    "properties": {
        "role": {
            "type": "string",
            "enum": [
                "agent", "patient", "theme", "recipient", "source",
                "destination", "instrument", "location", "path",
                "beneficiary", "companion", "experiencer", "owner",
                "holder", "container", "cause", "result",
            ],
        },
        "mention": _MENTION_SCHEMA,
    },
}

_ACTION_FRAME_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["predicate", "family", "arguments"],
    "properties": {
        "predicate": {
            "type": "string",
            "description": (
                "Copy a contiguous literal surface form from the current player message "
                "and its source_excerpt. Preserve conjugation, person, tense, number, "
                "clitics and accents; do not lemmatize, use an infinitive or paraphrase."
            ),
            "minLength": 1,
            "maxLength": 120,
        },
        "family": {
            "type": "string",
            "description": (
                "Use communication for linguistic acts such as asking, telling, speaking, "
                "whispering or replying. Use interaction for non-linguistic physical "
                "manipulation/contact; do not use it as a generic family for speech acts."
            ),
            "enum": [
                "movement", "communication", "perception", "interaction",
                "transfer", "item_use", "combat", "social", "state_change",
                "creation", "resource", "other", "unknown",
            ],
        },
        "arguments": {
            "type": "array",
            "maxItems": 12,
            "items": _ACTION_ARGUMENT_SCHEMA,
        },
    },
}

_RELATION_CLAIM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "step_index", "subject", "predicate", "object", "relation_family",
        "polarity", "modality", "source_excerpt", "attributed_to",
        "temporal_expression",
    ],
    "properties": {
        "step_index": {"type": "integer", "minimum": 0, "maximum": 7},
        "subject": _MENTION_SCHEMA,
        "predicate": {
            "type": "string",
            "description": (
                "Literal surface predicate copied from the current player evidence. "
                "Preserve its written form; do not lemmatize, translate or paraphrase."
            ),
            "minLength": 1,
            "maxLength": 120,
        },
        "object": _MENTION_SCHEMA,
        "relation_family": {
            "type": "string",
            "enum": [
                "kinship", "ownership", "possession", "membership",
                "employment", "allegiance", "friendship", "hostility",
                "spatial", "containment", "part_of", "knowledge",
                "obligation", "protection", "service", "other", "unknown",
            ],
        },
        "polarity": {"type": "string", "enum": ["positive", "negative", "uncertain"]},
        "modality": {
            "type": "string",
            "enum": [
                "attempted", "completed", "observed", "planned", "conditional",
                "question", "dialogue", "reported", "negated", "correction",
                "unknown",
            ],
        },
        "source_excerpt": {
            "type": "string",
            "description": (
                "One contiguous, verbatim substring of the current player message. "
                "It must contain this claim's literal predicate and every mention "
                "used by the claim; never stitch text from history."
            ),
            "minLength": 1,
            "maxLength": 300,
        },
        "attributed_to": {"anyOf": [_MENTION_SCHEMA, {"type": "null"}]},
        "temporal_expression": {
            "type": ["string", "null"],
            "description": (
                "Literal temporal expression from the current player message and this "
                "claim's source_excerpt. Do not infer or copy a time from conversation history."
            ),
            "maxLength": 120,
        },
    },
}

INTENT_MECHANICS_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent_analysis", "mechanics_decision"],
    "properties": {
        "intent_analysis": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version", "category", "steps", "active_step_index",
                "requires_clarification", "clarification_question",
                "relation_claims",
            ],
            "properties": {
                "schema_version": {"type": "integer", "const": 2},
                "category": {
                    "type": "string",
                    "description": (
                        "Classify the global speech act, not just verb tense. action is "
                        "the player's current attempt; dialogue is an in-fiction speech act "
                        "(including an indirect question addressed to a character); question "
                        "is a direct or implicit request for information/clarification from the "
                        "DM/narrator; report is an observed or recounted event, including "
                        "a non-speech NPC action; plan is future/conditional. "
                        "Only action and mixed may have a non-null active_step_index."
                    ),
                    "enum": [
                        "action", "question", "dialogue", "report",
                        "plan", "correction", "mixed", "unknown",
                    ],
                },
                "steps": {
                    "type": "array",
                    "maxItems": 8,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "index", "source_excerpt", "actor", "action",
                            "modality", "polarity", "reported_outcome",
                            "target_mentions", "attributed_to", "action_frame",
                        ],
                        "properties": {
                            "index": {
                                "type": "integer",
                                "description": (
                                    "Zero-based position in the ordered steps array: "
                                    "first step 0, second step 1, and so on."
                                ),
                                "minimum": 0,
                                "maximum": 7,
                            },
                            "source_excerpt": {
                                "type": "string",
                                "description": (
                                    "One contiguous, verbatim substring of the current player message. "
                                    "Include the action predicate and all mentions for this step. "
                                    "For callbacks, include the callback phrase and its action clause."
                                ),
                                "minLength": 1,
                                "maxLength": 300,
                            },
                            "actor": {
                                "type": "string",
                                "enum": ["player", "npc", "other", "unknown"],
                            },
                            "action": {
                                "type": "string",
                                "description": (
                                    "Concise semantic description of the step. It may explain a "
                                    "uniquely recoverable ellipsis, but is not literal evidence "
                                    "for predicate, mention or source_excerpt fields."
                                ),
                                "minLength": 1,
                                "maxLength": 500,
                            },
                            "modality": {
                                "type": "string",
                                "enum": [
                                    "attempted", "completed", "observed", "planned",
                                    "conditional", "question", "dialogue", "reported",
                                    "negated", "correction", "unknown",
                                ],
                            },
                            "polarity": {
                                "type": "string",
                                "enum": ["positive", "negative", "uncertain"],
                            },
                            "reported_outcome": {
                                "type": "string",
                                "enum": [
                                    "success", "failure", "partial",
                                    "not_claimed", "uncertain",
                                ],
                            },
                            "target_mentions": {
                                "type": "array",
                                "description": (
                                    "Literal mentions from this player message and source_excerpt. "
                                    "Keep pronouns/demonstratives as written; do not replace them "
                                    "with entities recovered from history."
                                ),
                                "maxItems": 6,
                                "items": {"type": "string", "minLength": 1, "maxLength": 120},
                            },
                            "attributed_to": {
                                "type": ["string", "null"],
                                "description": (
                                    "Literal attribution mention from current player evidence. "
                                    "Use null when it appears only in history, discourse context "
                                    "or an unresolved pronoun."
                                ),
                                "maxLength": 120,
                            },
                            "action_frame": _ACTION_FRAME_SCHEMA,
                        },
                    },
                },
                "active_step_index": {
                    "type": ["integer", "null"],
                    "description": (
                        "Must be null for question, dialogue, report, plan, "
                        "correction and unknown categories. Use a step index "
                        "only when category is action or mixed."
                    ),
                    "minimum": 0,
                    "maximum": 7,
                },
                "requires_clarification": {"type": "boolean"},
                "clarification_question": {
                    "type": ["string", "null"],
                    "maxLength": 300,
                },
                "relation_claims": {
                    "type": "array",
                    "maxItems": 8,
                    "items": _RELATION_CLAIM_SCHEMA,
                },
            },
        },
        "mechanics_decision": {
            "type": "object",
            "additionalProperties": False,
            "required": ["decision"],
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": [
                        "none", "clarification", "ability_check",
                        "skill_check", "saving_throw",
                    ],
                },
                "question": {"type": "string", "maxLength": 300},
                "dc": {"type": "integer", "minimum": 1, "maximum": 30},
                "advantage": {"type": "boolean"},
                "disadvantage": {"type": "boolean"},
                "modifier": {"type": "integer", "minimum": -10, "maximum": 10},
                "reason": {"type": "string", "maxLength": 500},
                "skill": {"type": "string", "maxLength": 80},
                "ability": {"type": ["string", "null"], "maxLength": 40},
            },
        },
    },
}

_PENDING_CORRECTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "step_index", "slot", "previous_value", "replacement",
        "source_excerpt", "argument_role", "relation_claim_index",
    ],
    "properties": {
        "step_index": {"type": "integer", "minimum": 0, "maximum": 7},
        "slot": {
            "type": "string",
            "enum": [
                "target_mention", "action_argument",
                "relation_subject", "relation_object",
            ],
        },
        "previous_value": {"type": "string", "minLength": 1, "maxLength": 120},
        "replacement": _MENTION_SCHEMA,
        "source_excerpt": {"type": "string", "minLength": 1, "maxLength": 300},
        "argument_role": {
            "type": ["string", "null"],
            "enum": [
                "agent", "patient", "theme", "recipient", "source",
                "destination", "instrument", "location", "path",
                "beneficiary", "companion", "experiencer", "owner",
                "holder", "container", "cause", "result", None,
            ],
        },
        "relation_claim_index": {
            "type": ["integer", "null"],
            "minimum": 0,
            "maximum": 7,
        },
    },
}

# Used only while resolving an uncommitted clarification. The ordinary turn
# path keeps the original schema and provider-call shape unchanged.
INTENT_MECHANICS_CORRECTION_RESPONSE_SCHEMA = deepcopy(
    INTENT_MECHANICS_RESPONSE_SCHEMA
)
INTENT_MECHANICS_CORRECTION_RESPONSE_SCHEMA["required"] = [
    "intent_analysis",
    "mechanics_decision",
    "pending_corrections",
]
INTENT_MECHANICS_CORRECTION_RESPONSE_SCHEMA["properties"][
    "pending_corrections"
] = {
    "type": "array",
    "maxItems": 4,
    "items": _PENDING_CORRECTION_SCHEMA,
}

# Role-specific contracts keep interpretation independent from mechanics.
# The semantic v2 payload remains byte-for-byte compatible with the nested
# analysis schema used by the former combined response.
INTENT_ANALYSIS_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent_analysis"],
    "properties": {
        "intent_analysis": deepcopy(
            INTENT_MECHANICS_RESPONSE_SCHEMA["properties"]["intent_analysis"]
        ),
    },
}

INTENT_CORRECTION_RESPONSE_SCHEMA = deepcopy(INTENT_ANALYSIS_RESPONSE_SCHEMA)
INTENT_CORRECTION_RESPONSE_SCHEMA["required"] = [
    "intent_analysis",
    "pending_corrections",
]
INTENT_CORRECTION_RESPONSE_SCHEMA["properties"]["pending_corrections"] = {
    "type": "array",
    "maxItems": 4,
    "items": _PENDING_CORRECTION_SCHEMA,
}

MECHANICS_ONLY_RESPONSE_SCHEMA = deepcopy(
    INTENT_MECHANICS_RESPONSE_SCHEMA["properties"]["mechanics_decision"]
)
