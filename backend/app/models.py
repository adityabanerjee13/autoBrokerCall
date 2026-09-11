"""Pydantic models for the five collections plus the API DTOs.

Field lists mirror the handoff spec exactly. Do not add or rename fields.
"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

LeadType = Literal["renter", "lender"]
LeadStatus = Literal[
    "New", "Queued", "Calling", "Contacted", "Qualified",
    "Appointment Set", "Escalated", "Closed", "Unqualified",
]
Furnishing = Literal["semi", "full", "unfurnished"]
PropertyStatus = Literal["available", "shown", "under_offer", "let", "paused"]
CallStatus = Literal["in_progress", "completed", "failed"]
AnalysisStatus = Literal["pending", "done", "failed"]
MessageStatus = Literal["draft", "sending", "sent", "partial", "failed"]
ChannelStatus = Literal["pending", "sent", "failed"]
SafetyVerdict = Literal["pass", "warn", "fail"]
Temperature = Literal["hot", "warm", "cold"]
MemoryKind = Literal[
    "preference", "constraint", "rejection_reason", "relationship",
    "communication_style", "commitment", "sensitivity",
]
EscalationReason = Literal[
    "DISCRIMINATORY_FILTER", "CASH_RENT_REQUEST", "PAYMENT_REQUEST",
    "HUMAN_REQUESTED", "OUT_OF_SCOPE", "LEGAL_OR_DISPUTE", "DISTRESS_OR_HOSTILITY",
]

ESCALATION_REASONS: tuple[str, ...] = (
    "DISCRIMINATORY_FILTER", "CASH_RENT_REQUEST", "PAYMENT_REQUEST",
    "HUMAN_REQUESTED", "OUT_OF_SCOPE", "LEGAL_OR_DISPUTE", "DISTRESS_OR_HOSTILITY",
)


# ---------------------------------------------------------------- collections

class Lead(BaseModel):
    lead_id: str
    created_at: datetime
    first_name: str
    last_name: str
    email: str
    phone: str
    lead_type: LeadType
    lead_status: LeadStatus

    monthly_rent_min: int | None = None
    monthly_rent_max: int | None = None
    property_type: str | None = None
    bhk_config: str | None = None
    furnishing: Furnishing | None = None
    preferred_areas: list[str] = Field(default_factory=list)

    subject_property_address: str | None = None

    first_contact_date: datetime | None = None
    last_contact_date: datetime | None = None
    liked_property_ids: list[str] = Field(default_factory=list)
    shown_property_ids: list[str] = Field(default_factory=list)
    showings_count: int = 0
    appointment_datetime: datetime | None = None


class Property(BaseModel):
    property_id: str
    owner_lead_id: str
    address: str
    locality: str
    property_type: str
    bhk_config: str
    furnishing: Furnishing
    monthly_rent: int
    deposit_months: int
    status: PropertyStatus
    verified_facts: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MemoryEntry(BaseModel):
    kind: MemoryKind
    text: str
    call_id: str
    created_at: datetime


class LeadMemory(BaseModel):
    """Agent-private. No API route may return this model."""

    lead_id: str
    version: int
    memory_block: str
    block_tokens: int
    entries: list[MemoryEntry] = Field(default_factory=list)
    updated_at: datetime


class TranscriptTurn(BaseModel):
    idx: int
    role: Literal["agent", "lead"]
    text: str
    at_ms: int


class ToolCallRecord(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    allowed: bool
    reason: str | None = None
    at_ms: int


class CallMetrics(BaseModel):
    agent_talk_ratio: float = 0.0
    avg_latency_ms: int = 0
    dead_air_events: int = 0
    turn_count: int = 0


class ObjectionHandling(BaseModel):
    score: int
    rationale: str
    turns: list[int] = Field(default_factory=list)


class ConversionTrack(BaseModel):
    fields_captured: list[str] = Field(default_factory=list)
    fields_missing: list[str] = Field(default_factory=list)
    completeness: float = 0.0
    next_step_secured: bool = False
    next_step: str | None = None
    objection_handling: ObjectionHandling | None = None
    lead_temperature: Temperature = "cold"
    proposed_status: LeadStatus | None = None
    track_score: float = 0.0


class Violation(BaseModel):
    rule: str
    turn: int
    quote: str
    explanation: str


class EscalationJudgement(BaseModel):
    should_have: bool = False
    did: bool = False
    reason: str | None = None
    miss_type: Literal["false_negative", "false_positive"] | None = None


class UnverifiedClaim(BaseModel):
    turn: int
    claim: str
    property_id: str | None = None


class SafetyTrack(BaseModel):
    verdict: SafetyVerdict = "pass"
    violations: list[Violation] = Field(default_factory=list)
    escalation: EscalationJudgement = Field(default_factory=EscalationJudgement)
    unverified_claims: list[UnverifiedClaim] = Field(default_factory=list)
    pressure_flags: list[str] = Field(default_factory=list)


class CallAnalysis(BaseModel):
    status: AnalysisStatus = "pending"
    deployment: str | None = None
    analyzed_at: datetime | None = None
    conversion: ConversionTrack | None = None
    safety: SafetyTrack | None = None


class Call(BaseModel):
    call_id: str
    lead_id: str
    direction: Literal["outbound"] = "outbound"
    # Which transport carried this call: dograh or mock. Stored per call rather
    # than read from settings, because the setting can change between a call
    # being placed and being looked at again.
    transport: str = "mock"
    # Dograh's id for the run that carried this call. The carrier's own call
    # ids live in Dograh, not here - this app never sees them.
    dograh_run_id: int | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_s: int | None = None
    status: CallStatus = "in_progress"

    transcript: list[TranscriptTurn] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)

    escalated: bool = False
    escalation_reason: EscalationReason | None = None
    escalated_at: datetime | None = None

    metrics: CallMetrics = Field(default_factory=CallMetrics)
    analysis: CallAnalysis = Field(default_factory=CallAnalysis)
    recording_url: str | None = None


class Channel(BaseModel):
    status: ChannelStatus = "pending"
    provider_id: str | None = None
    sent_at: datetime | None = None
    error: str | None = None


class WhatsAppChannel(Channel):
    body: str


class EmailChannel(Channel):
    subject: str
    body_text: str


class Message(BaseModel):
    message_id: str
    call_id: str
    lead_id: str
    whatsapp: WhatsAppChannel
    email: EmailChannel
    status: MessageStatus = "draft"
    triggered_by: str | None = None
    triggered_at: datetime | None = None
    created_at: datetime


# ------------------------------------------------------------------ API DTOs

class StartCallRequest(BaseModel):
    lead_id: str


class StartCallResponse(BaseModel):
    call_id: str
    status: str


class LeadRow(BaseModel):
    lead_id: str
    first_name: str
    last_name: str
    lead_type: LeadType
    lead_status: str
    phone: str
    monthly_rent_min: int | None = None
    monthly_rent_max: int | None = None
    bhk_config: str | None = None
    preferred_areas: list[str] = Field(default_factory=list)
    subject_property_address: str | None = None
    created_at: datetime
    last_contact_date: datetime | None = None


class ToolChip(BaseModel):
    name: str
    allowed: bool
    reason: str | None = None


class ActiveCall(BaseModel):
    call_id: str
    lead: LeadRow
    started_at: datetime
    elapsed_s: int
    transcript: list[TranscriptTurn]
    tool_calls: list[ToolChip]
    escalated: bool
    escalation_reason: str | None = None


class MessagePreview(BaseModel):
    message_id: str
    status: str
    whatsapp_preview: str
    email_subject: str


class CompletedCall(BaseModel):
    call_id: str
    lead: LeadRow
    ended_at: datetime | None
    duration_s: int
    escalated: bool
    escalation_reason: str | None = None
    analysis_status: AnalysisStatus
    message: MessagePreview | None = None


class ClientProperty(BaseModel):
    property_id: str
    address: str
    bhk_config: str
    monthly_rent: int
    status: str
    furnishing: str


class ClientInterest(BaseModel):
    property_id: str
    shown_count: int
    liked_count: int


class ClientUpcoming(BaseModel):
    first_name: str
    property_id: str
    appointment_datetime: datetime


class ClientDashboard(BaseModel):
    properties: list[ClientProperty]
    interest: list[ClientInterest]
    upcoming: list[ClientUpcoming]


class LenderOption(BaseModel):
    lead_id: str
    name: str


class AnalysisRow(BaseModel):
    call_id: str
    lead_name: str
    ended_at: datetime | None
    duration_s: int
    conversion_score: float
    completeness: float
    next_step_secured: bool
    lead_temperature: Temperature
    safety_verdict: SafetyVerdict
    violation_count: int
    escalated: bool


class ManagerStats(BaseModel):
    calls_today: int
    escalation_rate: float
    safety_fails: int
    avg_completeness: float
    avg_talk_ratio: float


class SendResponse(BaseModel):
    status: str


class NewLeadRequest(BaseModel):
    """A lead typed in by hand on the manager dashboard.

    Only what a person could reasonably know before the first call. The
    qualifying fields are deliberately optional for a renter - capturing them is
    the agent's job, and pre-filling a guess would be recorded as if the caller
    had said it.
    """

    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(default="", max_length=60)
    email: str = Field(default="", max_length=200)
    phone: str = Field(min_length=8, max_length=20)
    lead_type: LeadType

    # renter, all optional
    monthly_rent_min: int | None = Field(default=None, ge=0, le=100_000_000)
    monthly_rent_max: int | None = Field(default=None, ge=0, le=100_000_000)
    bhk_config: str | None = Field(default=None, max_length=20)
    furnishing: Furnishing | None = None
    preferred_areas: list[str] = Field(default_factory=list, max_length=10)

    # lender
    subject_property_address: str | None = Field(default=None, max_length=200)


class NewLeadResponse(BaseModel):
    lead_id: str
    lead_status: str
