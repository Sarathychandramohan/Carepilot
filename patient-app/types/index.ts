export type UrgencyLevel = 'routine' | 'soon' | 'urgent';
export type IntentType = 'symptom_query' | 'medication_query' | 'report_query' | 'appointment_request' | 'follow_up';
export type ConsultationStatus = 'draft' | 'sending' | 'processing' | 'doctor_review' | 'approved' | 'rejected' | 'error';
export type ThreadStatus = 'awaiting_doctor' | 'approved' | 'patient_replied';
export type AppointmentStatus = 'requested' | 'pending' | 'confirmed' | 'rescheduled' | 'cancelled' | 'completed' | 'rejected';
export type AppointmentRequestStatus = 'pending_doctor_approval' | 'approved' | 'denied' | 'alternative_proposed';
export type NotificationCategory = 'consultation' | 'appointment' | 'medical_records' | 'system';

export interface Patient {
  id: string;
  firstName: string;
  lastName: string;
  dateOfBirth: string;
  gender: 'M' | 'F';
  age: number;
  conditions: Condition[];
  medications: Medication[];
  allergies: Allergy[];
}

export interface Condition {
  id: string;
  description: string;
  startDate: string;
  stopDate?: string;
  active: boolean;
}

export interface LabResult {
  id: string;
  patientId: string;
  testName: string;
  value: number;
  unit: string;
  date: string;
  previousValue?: number;
  referenceMin?: number;
  referenceMax?: number;
  trend?: 'increasing' | 'decreasing' | 'stable';
  trendDirection?: 'rising' | 'falling' | 'stable';
  trendReadingsCount?: number;
  isOutOfRange?: boolean;
  history?: Array<{ date: string; value: number }>;
}

export interface Medication {
  id: string;
  patientId: string;
  name: string;
  dosage: string;
  frequency: string;
  startDate: string;
  stopDate?: string;
  active: boolean;
  reasonDescription?: string;
}

export interface Allergy {
  id: string;
  description: string;
  severity?: string;
  type?: string;
}

export interface Encounter {
  id: string;
  patientId: string;
  date: string;
  type: string;
  encounterClass: string;
  reasonDescription: string;
  description: string;
}

export interface Document {
  id: string;
  patientId: string;
  name: string;
  category: 'lab_report' | 'prescription' | 'medical_report' | 'identity' | 'other';
  uploadedAt: string;
  size?: string;
  uri?: string;
}

export interface Appointment {
  id: string;
  patientId: string;
  doctorName: string;
  date: string;
  time: string;
  reason: string;
  status: AppointmentStatus;
  notes?: string;
}

export interface AppointmentRequest {
  id: string;
  patientId: string;
  patientName: string;
  requestType: 'new' | 'reschedule';
  originalAppointmentId?: string;
  requestedDate: string;
  requestedTime: string;
  reason: string;
  status: AppointmentRequestStatus;
  doctorResponse?: string;
  proposedAlternativeDate?: string;
  proposedAlternativeTime?: string;
  createdAt: string;
  updatedAt: string;
}

export interface Message {
  id: string;
  consultationId: string;
  role: 'patient' | 'system' | 'doctor';
  content: string;
  timestamp: string;
  status?: ConsultationStatus;
}

export interface Citation {
  id: string;
  title: string;
  source: string;
  sourceType: string;
  date?: string;
  url?: string;
  excerpt?: string;
}

export interface AIAnalysis {
  intent: IntentType;
  urgency: UrgencyLevel;
  urgencyScore: number;
  patientContextRetrieved: boolean;
  knowledgeContextRetrieved: boolean;
  isHighPriorityAlert?: boolean;
  isRedFlagOverride?: boolean;
  alertReason?: string;
}

export interface AIDraft {
  content: string;
  generatedAt: string;
  citations: Citation[];
}

export interface DoctorReview {
  doctorId: string;
  doctorName: string;
  action: 'approved' | 'rejected';
  editedContent?: string;
  originalContent?: string;
  editCategory?: 'factual_correction' | 'added_caution' | 'tone_change' | 'no_change';
  editDistance?: number;
  reason?: string;
  reviewedAt: string;
}

export interface Consultation {
  id: string;
  patientId: string;
  patientName: string;
  query: string;
  status: ConsultationStatus;
  threadStatus?: ThreadStatus;
  intent?: IntentType;
  urgency?: UrgencyLevel;
  aiAnalysis?: AIAnalysis;
  aiDraft?: AIDraft;
  doctorReview?: DoctorReview;
  finalResponse?: string;
  messages: Message[];
  turnCount?: number;
  isHighPriorityAlert?: boolean;
  isRedFlagOverride?: boolean;
  alertReason?: string;
  createdAt: string;
  updatedAt: string;
}

export interface AppNotification {
  id: string;
  userId: string;
  category: NotificationCategory;
  title: string;
  body: string;
  read: boolean;
  relatedId?: string;
  createdAt: string;
}

export interface Doctor {
  id: string;
  name: string;
  specialization: string;
  email: string;
}
