"""JSON schemas for structured output.

Azure `strict: true` requires every property to be listed in `required` and
`additionalProperties: false` on every object. Nullability is expressed as a
type union rather than by omitting the key.
"""
from app.models import ESCALATION_REASONS

LEAD_STATUSES = [
    "New", "Queued", "Calling", "Contacted", "Qualified",
    "Appointment Set", "Escalated", "Closed", "Unqualified",
]

CONVERSION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fields_captured": {"type": "array", "items": {"type": "string"}},
        "fields_missing": {"type": "array", "items": {"type": "string"}},
        "completeness": {"type": "number"},
        "next_step_secured": {"type": "boolean"},
        "next_step": {"type": ["string", "null"]},
        "objection_handling": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "score": {"type": "integer"},
                "rationale": {"type": "string"},
                "turns": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["score", "rationale", "turns"],
        },
        "lead_temperature": {"type": "string", "enum": ["hot", "warm", "cold"]},
        "proposed_status": {"type": ["string", "null"], "enum": [*LEAD_STATUSES, None]},
        "track_score": {"type": "number"},
    },
    "required": [
        "fields_captured", "fields_missing", "completeness", "next_step_secured",
        "next_step", "objection_handling", "lead_temperature", "proposed_status",
        "track_score",
    ],
}

SAFETY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "warn", "fail"]},
        "violations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "rule": {"type": "string"},
                    "turn": {"type": "integer"},
                    "quote": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["rule", "turn", "quote", "explanation"],
            },
        },
        "escalation": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "should_have": {"type": "boolean"},
                "did": {"type": "boolean"},
                "reason": {"type": ["string", "null"], "enum": [*ESCALATION_REASONS, None]},
                "miss_type": {
                    "type": ["string", "null"],
                    "enum": ["false_negative", "false_positive", None],
                },
            },
            "required": ["should_have", "did", "reason", "miss_type"],
        },
        "unverified_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "turn": {"type": "integer"},
                    "claim": {"type": "string"},
                    "property_id": {"type": ["string", "null"]},
                },
                "required": ["turn", "claim", "property_id"],
            },
        },
        "pressure_flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "verdict", "violations", "escalation", "unverified_claims", "pressure_flags"
    ],
}

MEMORY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "memory_block": {"type": "string"},
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": [
                            "preference", "constraint", "rejection_reason",
                            "relationship", "communication_style", "commitment",
                            "sensitivity",
                        ],
                    },
                    "text": {"type": "string"},
                },
                "required": ["kind", "text"],
            },
        },
    },
    "required": ["memory_block", "entries"],
}

MESSAGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "whatsapp_body": {"type": "string"},
        "email_subject": {"type": "string"},
        "email_body_text": {"type": "string"},
    },
    "required": ["whatsapp_body", "email_subject", "email_body_text"],
}
