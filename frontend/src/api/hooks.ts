import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import { api } from "./client";
import type {
  ActiveCall,
  AnalysisRow,
  CallDetail,
  ClientDashboard,
  CompletedCall,
  LeadRow,
  LenderOption,
  ManagerStats,
  NewLead,
  NewLeadResponse,
} from "./types";

// Refetch intervals are the polling contract with the backend: the live call
// panel needs to feel live, everything else does not.
export const useQueue = (): UseQueryResult<LeadRow[]> =>
  useQuery({
    queryKey: ["queue"],
    queryFn: () => api.get<LeadRow[]>("/api/broker/queue"),
    refetchInterval: 5000,
  });

export const useActiveCall = (): UseQueryResult<ActiveCall | null> =>
  useQuery({
    queryKey: ["active"],
    queryFn: () => api.get<ActiveCall | null>("/api/broker/active"),
    refetchInterval: 1000,
  });

export const useCompleted = (): UseQueryResult<CompletedCall[]> =>
  useQuery({
    queryKey: ["completed"],
    queryFn: () => api.get<CompletedCall[]>("/api/broker/completed"),
    refetchInterval: 5000,
  });

export const useLenders = (): UseQueryResult<LenderOption[]> =>
  useQuery({
    queryKey: ["lenders"],
    queryFn: () => api.get<LenderOption[]>("/api/client/lenders"),
  });

export const useClientDashboard = (
  leadId: string | null
): UseQueryResult<ClientDashboard> =>
  useQuery({
    queryKey: ["client", leadId],
    queryFn: () => api.get<ClientDashboard>(`/api/client/${leadId}/dashboard`),
    enabled: Boolean(leadId),
    refetchInterval: 10000,
  });

export const useManagerStats = (): UseQueryResult<ManagerStats> =>
  useQuery({
    queryKey: ["manager-stats"],
    queryFn: () => api.get<ManagerStats>("/api/manager/stats"),
    refetchInterval: 10000,
  });

export const useAnalysis = (): UseQueryResult<AnalysisRow[]> =>
  useQuery({
    queryKey: ["manager-analysis"],
    queryFn: () => api.get<AnalysisRow[]>("/api/manager/analysis"),
    refetchInterval: 10000,
  });

export const useCall = (callId: string | null): UseQueryResult<CallDetail> =>
  useQuery({
    queryKey: ["call", callId],
    queryFn: () => api.get<CallDetail>(`/api/calls/${callId}`),
    enabled: Boolean(callId),
  });

export function useStartCall() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (leadId: string) =>
      api.post<{ call_id: string; status: string }>("/api/calls/start", {
        lead_id: leadId,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["queue"] });
      qc.invalidateQueries({ queryKey: ["active"] });
    },
  });
}

export function useSendMessage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) =>
      api.post<{ status: string }>(`/api/messages/${messageId}/send`),
    onSettled: () => {
      // Settled, not success: a 409 from a double-click also means the row on
      // screen is stale and should be refetched.
      qc.invalidateQueries({ queryKey: ["completed"] });
    },
  });
}

export function useCreateLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (lead: NewLead) =>
      api.post<NewLeadResponse>("/api/manager/leads", lead),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["queue"] });
    },
  });
}
