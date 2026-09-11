// Mirrors backend/app/models.py API DTOs exactly. Nothing here describes
// lead_memory - there is no endpoint that returns it, by design.

export type LeadType = "renter" | "lender";

export type LeadRow = {
  lead_id: string;
  first_name: string;
  last_name: string;
  lead_type: LeadType;
  lead_status: string;
  phone: string;
  monthly_rent_min: number | null;
  monthly_rent_max: number | null;
  bhk_config: string | null;
  preferred_areas: string[];
  subject_property_address: string | null;
  created_at: string;
  last_contact_date: string | null;
};

export type TranscriptTurn = {
  idx: number;
  role: "agent" | "lead";
  text: string;
  at_ms: number;
};

export type ToolChip = {
  name: string;
  allowed: boolean;
  reason: string | null;
};

export type CallStatus = "ringing" | "in_progress" | "completed" | "failed";

export type ActiveCall = {
  call_id: string;
  lead: LeadRow;
  status: CallStatus;
  started_at: string;
  elapsed_s: number;
  transcript: TranscriptTurn[];
  tool_calls: ToolChip[];
  escalated: boolean;
  escalation_reason: string | null;
};

export type MessageStatus = "draft" | "sending" | "sent" | "partial" | "failed";
export type AnalysisStatus = "pending" | "done" | "failed";

export type CompletedCall = {
  call_id: string;
  lead: LeadRow;
  ended_at: string | null;
  duration_s: number;
  escalated: boolean;
  escalation_reason: string | null;
  analysis_status: AnalysisStatus;
  message: {
    message_id: string;
    status: MessageStatus;
    whatsapp_preview: string;
    email_subject: string;
  } | null;
};

export type ClientDashboard = {
  properties: {
    property_id: string;
    address: string;
    bhk_config: string;
    monthly_rent: number;
    status: string;
    furnishing: string;
  }[];
  interest: { property_id: string; shown_count: number; liked_count: number }[];
  upcoming: {
    first_name: string;
    property_id: string;
    appointment_datetime: string;
  }[];
};

export type LenderOption = { lead_id: string; name: string };

export type SafetyVerdict = "pass" | "warn" | "fail";
export type Temperature = "hot" | "warm" | "cold";

export type AnalysisRow = {
  call_id: string;
  lead_name: string;
  ended_at: string | null;
  duration_s: number;
  conversion_score: number;
  completeness: number;
  next_step_secured: boolean;
  lead_temperature: Temperature;
  safety_verdict: SafetyVerdict;
  violation_count: number;
  escalated: boolean;
};

export type ManagerStats = {
  calls_today: number;
  escalation_rate: number;
  safety_fails: number;
  avg_completeness: number;
  avg_talk_ratio: number;
};

// The full call document, as returned by GET /api/calls/{id}. Used by the
// manager drill-down drawer.
export type CallDetail = {
  call_id: string;
  lead_id: string;
  lead: { first_name: string; last_name: string; lead_type: LeadType; phone: string } | null;
  started_at: string;
  ended_at: string | null;
  duration_s: number | null;
  status: string;
  transcript: TranscriptTurn[];
  tool_calls: { name: string; args: Record<string, unknown>; allowed: boolean; reason: string | null }[];
  escalated: boolean;
  escalation_reason: string | null;
  metrics: {
    agent_talk_ratio: number;
    avg_latency_ms: number;
    dead_air_events: number;
    turn_count: number;
  };
  analysis: {
    status: AnalysisStatus;
    deployment: string | null;
    analyzed_at: string | null;
    conversion: {
      fields_captured: string[];
      fields_missing: string[];
      completeness: number;
      next_step_secured: boolean;
      next_step: string | null;
      objection_handling: { score: number; rationale: string; turns: number[] } | null;
      lead_temperature: Temperature;
      proposed_status: string | null;
      track_score: number;
    } | null;
    safety: {
      verdict: SafetyVerdict;
      violations: { rule: string; turn: number; quote: string; explanation: string }[];
      escalation: {
        should_have: boolean;
        did: boolean;
        reason: string | null;
        miss_type: string | null;
      };
      unverified_claims: { turn: number; claim: string; property_id: string | null }[];
      pressure_flags: string[];
    } | null;
  };
};

export type Furnishing = "semi" | "full" | "unfurnished";

export type NewLead = {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  lead_type: LeadType;
  monthly_rent_min: number | null;
  monthly_rent_max: number | null;
  bhk_config: string | null;
  furnishing: Furnishing | null;
  preferred_areas: string[];
  subject_property_address: string | null;
};

export type NewLeadResponse = { lead_id: string; lead_status: string };
