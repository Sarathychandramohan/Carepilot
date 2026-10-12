import { Patient, Consultation, AppNotification, Appointment } from '../../types';

export const HERO_PATIENT: Patient = {
  id: 'hero-001',
  firstName: 'Christian',
  lastName: 'Labadie',
  dateOfBirth: '1945-01-10',
  gender: 'M',
  age: 81,
  conditions: [
    { id: 'c1', description: 'Chronic Kidney Disease Stage 3', startDate: '2020-01-01', active: true },
    { id: 'c2', description: 'Hypertension', startDate: '2015-05-10', active: true },
    { id: 'c3', description: 'Type 2 Diabetes', startDate: '2010-08-20', active: true }
  ],
  medications: [
    { id: 'm1', patientId: 'hero-001', name: 'Lisinopril', dosage: '10mg', frequency: 'daily', startDate: '2015-05-15', active: true },
    { id: 'm2', patientId: 'hero-001', name: 'Metformin', dosage: '500mg', frequency: 'twice daily', startDate: '2010-08-25', active: true },
    { id: 'm3', patientId: 'hero-001', name: 'Furosemide', dosage: '40mg', frequency: 'daily', startDate: '2021-02-10', active: true }
  ],
  allergies: []
};

export const INITIAL_CONSULTATIONS: Consultation[] = [
  {
    id: 'cons-001',
    patientId: 'hero-001',
    patientName: 'Christian Labadie',
    query: 'Why is my recent blood test different from before?',
    status: 'doctor_review',
    intent: 'report_query',
    urgency: 'soon',
    messages: [
      { id: 'msg-1', consultationId: 'cons-001', role: 'patient', content: 'Why is my recent blood test different from before?', timestamp: new Date().toISOString(), status: 'doctor_review' }
    ],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  }
];

export const INITIAL_NOTIFICATIONS: AppNotification[] = [];
export const INITIAL_APPOINTMENTS: Appointment[] = [];
