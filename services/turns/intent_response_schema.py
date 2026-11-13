"""Ollama JSON Schema for the combined semantic-understanding/mechanics v2 response."""

_MENTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text", "kind_hint"],
    "properties": {
        "text": {"type": "string", "minLength": 1, "maxLength": 120},
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
        "predicate": {"type": "string", "minLength": 1, "maxLength": 120},
        "family": {
            "type": "string",
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
        "predicate": {"type": "string", "minLength": 1, "maxLength": 120},
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
        "source_excerpt": {"type": "string", "minLength": 1, "maxLength": 300},
        "attributed_to": {"anyOf": [_MENTION_SCHEMA, {"type": "null"}]},
        "temporal_expression": {"type": ["string", "null"], "maxLength": 120},
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
                            "index": {"type": "integer", "minimum": 0, "maximum": 7},
                            "source_excerpt": {"type": "string", "minLength": 1, "maxLength": 300},
                            "actor": {
                                "type": "string",
                                "enum": ["player", "npc", "other", "unknown"],
                            },
                            "action": {"type": "string", "minLength": 1, "maxLength": 500},
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
                                "maxItems": 6,
                                "items": {"type": "string", "minLength": 1, "maxLength": 120},
                            },
                            "attributed_to": {
                                "type": ["string", "null"],
                                "maxLength": 120,
                            },
                            "action_frame": _ACTION_FRAME_SCHEMA,
                        },
                    },
                },
                "active_step_index": {
                    "type": ["integer", "null"],
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
