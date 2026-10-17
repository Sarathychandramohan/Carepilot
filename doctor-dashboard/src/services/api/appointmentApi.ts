import { apiClient } from './apiClient';

export interface BackendAppointmentRequest {
  id: string;
  patientId: string;
  patientName: string;
  requestType: 'new' | 'reschedule';
  originalAppointmentId?: string;
  requestedDate: string;
  requestedTime: string;
  reason: string;
  status: 'pending_doctor_approval' | 'approved' | 'denied' | 'alternative_proposed';
  doctorResponse?: string;
  proposedAlternativeDate?: string;
  proposedAlternativeTime?: string;
  createdAt: string;
}

export const appointmentApi = {
  getRequests: (status?: string) =>
    apiClient.get<BackendAppointmentRequest[]>('/api/appointments/requests', {
      params: { status },
    }),

  respondRequest: (
    requestId: string,
    action: 'approve' | 'deny' | 'propose_alternative',
    doctorResponse?: string,
    proposedDate?: string,
    proposedTime?: string
  ) =>
    apiClient.put<BackendAppointmentRequest>(`/api/appointments/requests/${requestId}/respond`, undefined, {
      params: {
        action,
        doctor_response: doctorResponse,
        proposed_date: proposedDate,
        proposed_time: proposedTime,
      },
    }),
};
