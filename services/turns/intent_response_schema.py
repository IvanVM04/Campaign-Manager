"""Ollama JSON Schema for the combined language-understanding/mechanics response."""

INTENT_MECHANICS_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent_analysis", "mechanics_decision"],
    "properties": {
        "intent_analysis": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "category",
                "steps",
                "active_step_index",
                "requires_clarification",
                "clarification_question",
            ],
            "properties": {
                "schema_version": {"type": "integer", "const": 1},
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
                            "target_mentions", "attributed_to",
                        ],
                        "properties": {
                            "index": {"type": "integer", "minimum": 0, "maximum": 7},
                            "source_excerpt": {"type": "string", "minLength": 1, "maxLength": 300},
                            "actor": {"type": "string", "enum": ["player", "npc", "other", "unknown"]},
                            "action": {"type": "string", "maxLength": 500},
                            "modality": {
                                "type": "string",
                                "enum": [
                                    "attempted", "completed", "observed", "planned",
                                    "conditional", "question", "dialogue", "reported",
                                    "negated", "correction", "unknown",
                                ],
                            },
                            "polarity": {"type": "string", "enum": ["positive", "negative", "uncertain"]},
                            "reported_outcome": {
                                "type": "string",
                                "enum": ["success", "failure", "partial", "not_claimed", "uncertain"],
                            },
                            "target_mentions": {
                                "type": "array",
                                "maxItems": 6,
                                "items": {"type": "string", "minLength": 1, "maxLength": 120},
                            },
                            "attributed_to": {"type": ["string", "null"], "maxLength": 120},
                        },
                    },
                },
                "active_step_index": {"type": ["integer", "null"], "minimum": 0, "maximum": 7},
                "requires_clarification": {"type": "boolean"},
                "clarification_question": {"type": ["string", "null"], "maxLength": 300},
            },
        },
        "mechanics_decision": {
            "type": "object",
            "additionalProperties": False,
            "required": ["decision"],
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["none", "clarification", "ability_check", "skill_check", "saving_throw"],
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
