import { apiClient } from './apiClient';

export interface QueueItemResponse {
  id: string;
  patient_id: string;
  query_text: string;
  intent: string;
  urgency_final: 'routine' | 'soon' | 'urgent';
  is_high_priority: boolean;
  is_red_flag_override: boolean;
  validation_status: 'passed' | 'passed_with_warning' | 'passed_with_outlier_caveat' | 'manual_required';
  has_draft: boolean;
  faithfulness_score?: number;
  ablation_arm?: string;
  patient_ehr_mismatch_flag?: boolean;
  missing_context_flag?: boolean;
  created_at: string;
}

export interface QueueStatsResponse {
  total_pending: number;
  high_priority: number;
  red_flag_overrides: number;
  has_draft: number;
  by_validation_status: {
    passed: number;
    passed_with_warning: number;
    passed_with_outlier_caveat: number;
    manual_required: number;
  };
  by_ablation_arm: Record<string, number>;
}

export interface DoctorReviewPayload {
  doctor_action: 'approved' | 'edited' | 'rejected';
  final_response?: string;
  reject_reason?: string;
  edit_categories?: Record<string, number>;
  doctor_review_seconds?: number;
  opened_sources?: string[];
}

export interface DoctorReviewResponse {
  consultation_id: string;
  doctor_action: string;
  thread_status: string;
  final_response?: string;
  edit_categories: Record<string, number>;
  consultation_edit_weight: number;
  edit_distance_chars?: number;
  edit_distance_words?: number;
  edr_char?: number;
  edr_word?: number;
  doctor_reviewed_at: string;
}

export interface BackendConsultationDetail {
  id: string;
  patient_id: string;
  query_text: string;
  intent?: string;
  urgency_final?: 'routine' | 'soon' | 'urgent';
  validation_status?: 'passed' | 'passed_with_warning' | 'passed_with_outlier_caveat' | 'manual_required';
  thread_status: string;
  is_high_priority: boolean;
  is_red_flag_override: boolean;
  ai_draft?: {
    sentences?: Array<{ text: string; citations: string[] }>;
    overall_tone?: string;
    recommended_followup?: string;
    llm_model?: string;
    generation_latency_ms?: number;
  } | null;
  faithfulness_score?: number;
  citation_entailment_score?: number;
  ablation_arm?: string;
  llm_model?: string;
  generation_latency_ms?: number;
  doctor_action?: string;
  reject_reason?: string;
  final_response?: string;
  consultation_edit_weight?: number;
  edit_categories?: Record<string, number>;
  doctor_review_seconds?: number;
  doctor_reviewed_at?: string;
  delivered_at?: string;
  created_at: string;
}

export const consultationApi = {
  getQueue: (ablationArm?: string, limit = 50, offset = 0) =>
    apiClient.get<QueueItemResponse[]>('/api/queue', {
      params: { ablation_arm: ablationArm, limit, offset },
    }),

  getQueueStats: () =>
    apiClient.get<QueueStatsResponse>('/api/queue/stats'),

  getConsultation: (id: string) =>
    apiClient.get<BackendConsultationDetail>(`/api/consult/${id}`),

  submitReview: (id: string, payload: DoctorReviewPayload) =>
    apiClient.post<DoctorReviewResponse>(`/api/consult/${id}/review`, payload),

  deliverConsultation: (id: string) =>
    apiClient.post<{ consultation_id: string; patient_id: string; thread_status: string; final_response: string; delivered_at: string }>(
      `/api/consult/${id}/deliver`
    ),

  getDoctorAlerts: () =>
    apiClient.get<Array<{
      id: string;
      consultationId: string;
      patientId: string;
      patientName: string;
      urgency: string;
      isHighPriorityAlert: boolean;
      isRedFlagOverride: boolean;
      alertReason: string;
      createdAt: string;
    }>>('/api/notifications/doctor/alerts'),
};
