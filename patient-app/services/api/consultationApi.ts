import { Platform } from 'react-native';
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

export interface SttTranscribeResponse {
  text: string;
}

export const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || (Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000');

export const consultationApi = {
  submitConsultation: (patientId: string, queryText: string, language?: string) =>
    apiClient.post<SubmitConsultationResponse>('/api/consult', {
      patient_id: patientId,
      query_text: queryText,
      ablation_config: 'full',
      edit_memory: false,
      is_eval: false,
      language: language || 'en',
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

  // ── Speech-to-Text ──────────────────────────────────────────────
  transcribeAudio: async (audioFile: File, modelSize?: string) => {
    const formData = new FormData();
    formData.append('audio', audioFile);
    if (modelSize) formData.append('model_size', modelSize);

    const response = await fetch(`${API_BASE_URL}/api/voice/transcribe`, {
      method: 'POST',
      body: formData,
      headers: {
        'X-User-Role': 'patient',
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error((errorData && errorData.detail) || `STT failed: HTTP ${response.status}`);
    }

    return response.json();
  },

  // ── Text-to-Speech ──────────────────────────────────────────────
  synthesizeAudio: async (text: string, voice?: string) => {
    const response = await fetch(`${API_BASE_URL}/api/voice/synthesize`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Role': 'patient',
      },
      body: JSON.stringify({ text, voice: voice || 'en-US-JennyNeural' }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error((errorData && errorData.detail) || `TTS failed: HTTP ${response.status}`);
    }

    // TTS returns an audio file (MP3 blob)
    const blob = await response.blob();
    return URL.createObjectURL(blob);
  },
};