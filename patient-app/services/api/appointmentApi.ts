import { apiClient } from './apiClient';

export interface AppointmentRequestPayload {
  patient_id: string;
  request_type: 'new' | 'reschedule';
  requested_date: string;
  requested_time: string;
  reason: string;
  original_appointment_id?: string;
}

export interface AppointmentRequestResponse {
  id: string;
  patientId: string;
  requestType: string;
  status: string;
  message: string;
}

export const appointmentApi = {
  createRequest: (payload: AppointmentRequestPayload) =>
    apiClient.post<AppointmentRequestResponse>('/api/appointments/requests', undefined, {
      params: {
        patient_id: payload.patient_id,
        request_type: payload.request_type,
        requested_date: payload.requested_date,
        requested_time: payload.requested_time,
        reason: payload.reason,
        original_appointment_id: payload.original_appointment_id,
      },
    }),
};
