import { apiClient } from './apiClient';

export interface SubmitConsultationResponse {
  consultation_id: string;
  patient_id: string;
  intent?: string;
  urgency_final?: string;
  validation_status?: string;
  thread_status: string;
  is_high_priority: boolean;
  is_red_flag_override: boolean;
  has_draft: boolean;
  ablation_config: string;
  generation_latency_ms?: number;
  faithfulness_score?: number;
}

export interface PatientConsultationView {
  consultation_id: string;
  patient_id: string;
  thread_status: string;
  query_text: string;
  final_response?: string | null;
  message?: string | null;
  delivered_at?: string | null;
  created_at: string;
}

export const consultationApi = {
  submitConsultation: (patientId: string, queryText: string) =>
    apiClient.post<SubmitConsultationResponse>('/api/consult', {
      patient_id: patientId,
      query_text: queryText,
      ablation_config: 'full',
      edit_memory: false,
      is_eval: false,
    }),

  getPatientConsultation: (patientId: string, consultationId: string) =>
    apiClient.get<PatientConsultationView>(
      `/api/patient/${patientId}/consultations/${consultationId}`
    ),

  listPatientConsultations: (patientId: string, limit = 20, offset = 0) =>
    apiClient.get<PatientConsultationView[]>(
      `/api/patient/${patientId}/consultations`,
      { params: { limit, offset } }
    ),

  sendFollowUpReply: (conversationId: string, queryText: string) =>
    apiClient.post<{
      id: string;
      threadStatus: string;
      turnCount: number;
      status: string;
      message: string;
    }>('/api/conversations/reply', undefined, {
      params: { conversation_id: conversationId, query_text: queryText },
    }),
};
