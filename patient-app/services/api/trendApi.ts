import { apiClient } from './apiClient';

export interface LabReading {
  id: string;
  date: string;
  value: number;
  unit: string;
  isOutOfRange: boolean;
}

export interface LabTrendResponse {
  patientId: string;
  testName: string;
  unit: string;
  referenceMin?: number;
  referenceMax?: number;
  latestValue: number;
  latestDate: string;
  previousValue?: number;
  trendDirection: 'rising' | 'falling' | 'stable';
  readingsCount: number;
  isOutOfRange: boolean;
  readings: LabReading[];
}

export const trendApi = {
  getTrends: (patientId: string, testName = 'Creatinine') =>
    apiClient.get<LabTrendResponse>(`/api/reports/trends/${patientId}`, {
      params: { test_name: testName },
    }),
};
