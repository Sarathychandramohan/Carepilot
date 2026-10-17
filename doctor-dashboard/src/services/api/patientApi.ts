import { apiClient } from './apiClient';

export interface PatientListItem {
  id: string;
  firstName: string;
  lastName: string;
  gender: 'M' | 'F';
  age: number;
  dateOfBirth: string;
  city: string;
  state: string;
  conditionsCount: number;
  medicationsCount: number;
}

export interface PatientEhrData {
  id: string;
  firstName: string;
  lastName: string;
  dateOfBirth: string;
  gender: 'M' | 'F';
  age: number;
  address: string;
  city: string;
  state: string;
  conditions: Array<{
    id: string;
    description: string;
    startDate: string;
    stopDate?: string | null;
    active: boolean;
  }>;
  medications: Array<{
    id: string;
    patientId: string;
    name: string;
    dosage: string;
    frequency: string;
    startDate: string;
    stopDate?: string | null;
    active: boolean;
    reasonDescription?: string;
  }>;
  labResults: Array<{
    id: string;
    patientId: string;
    testName: string;
    value: number;
    unit: string;
    date: string;
    isOutOfRange: boolean;
    referenceMin?: number;
    referenceMax?: number;
  }>;
  encounters: Array<{
    id: string;
    patientId: string;
    date: string;
    type: string;
    encounterClass: string;
    description: string;
    reasonDescription?: string;
  }>;
  allergies: Array<{
    id: string;
    description: string;
    severity?: string;
    type?: string;
  }>;
}

export const patientApi = {
  getPatients: (search?: string, limit = 50, offset = 0) =>
    apiClient.get<PatientListItem[]>('/api/patients', {
      params: { search, limit, offset },
    }),

  getPatientEhr: (patientId: string) =>
    apiClient.get<PatientEhrData>(`/api/patient/${patientId}/ehr`),
};
