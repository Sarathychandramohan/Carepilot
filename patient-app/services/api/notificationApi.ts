import { apiClient } from './apiClient';

export interface PatientNotification {
  id: string;
  userId: string;
  category: 'consultation' | 'appointment' | 'system';
  title: string;
  body: string;
  read: boolean;
  relatedId?: string;
  createdAt: string;
}

export const notificationApi = {
  getNotifications: (patientId: string) =>
    apiClient.get<PatientNotification[]>(`/api/notifications/patient/${patientId}`),
};
