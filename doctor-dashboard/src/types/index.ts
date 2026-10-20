export type UrgencyLevel = 'routine' | 'soon' | 'urgent';
export type IntentType = 'symptom_query' | 'medication_query' | 'report_query' | 'appointment_request' | 'follow_up';
export type ConsultationStatus = 'draft' | 'sending' | 'processing' | 'doctor_review' | 'approved' | 'rejected' | 'error';
export type ThreadStatus = 'awaiting_doctor' | 'approved' | 'patient_replied';
export type AppointmentStatus = 'requested' | 'pending' | 'confirmed' | 'rescheduled' | 'cancelled' | 'completed' | 'rejected';
export type AppointmentRequestStatus = 'pending_doctor_approval' | 'approved' | 'denied' | 'alternative_proposed';
export type RejectReason = 'factual_correction' | 'insufficient_context' | 'unsafe_response' | 'poor_tone' | 'other';
export type EditCategory =
  | 'factual_correction'
  | 'missing_ehr_fact'
  | 'wrong_ehr_fact'
  | 'unsupported_medical_claim'
  | 'citation_error'
  | 'urgency_correction'
  | 'missing_caution'
  | 'tone_change'
  | 'unnecessary_content'
  | 'retrieval_error'
  | 'no_change'
  | 'other'
  | 'added_caution';

export type ValidationStatus =
  | 'passed'
  | 'passed_with_warning'
  | 'passed_with_outlier_caveat'
  | 'manual_required';

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
  lastConsultation?: string;
  pendingConsultationCount: number;
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
}

export interface Appointment {
  id: string;
  patientId: string;
  patientName: string;
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
  editCategory?: EditCategory;
  editDistance?: number;
  reason?: RejectReason;
  reasonNote?: string;
  reviewedAt: string;
}

export interface Message {
  id: string;
  consultationId: string;
  role: 'patient' | 'system' | 'doctor';
  content: string;
  timestamp: string;
  status?: ConsultationStatus;
}

export interface Consultation {
  id: string;
  patientId: string;
  patientName: string;
  patientAge?: number;
  patientGender?: string;
  query: string;
  status: ConsultationStatus;
  threadStatus?: ThreadStatus;
  intent?: IntentType;
  urgency?: UrgencyLevel;
  validationStatus?: ValidationStatus;
  faithfulnessScore?: number;
  citationEntailmentScore?: number;
  generationLatencyMs?: number;
  ablationArm?: string;
  language?: string;
  hasDraft?: boolean;
  aiDraftJson?: any;
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

export interface TimelineEvent {
  id: string;
  patientId: string;
  type: 'consultation' | 'lab' | 'encounter' | 'prescription' | 'appointment';
  date: string;
  title: string;
  description: string;
  relatedId?: string;
}

export interface AppNotification {
  id: string;
  userId: string;
  category: 'consultation' | 'appointment' | 'system';
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

export interface AnalyticsData {
  totalConsultations: number;
  approved: number;
  edited: number;
  rejected: number;
  acceptanceRate: number;
  avgEditDistance: number;
  editCategories: Array<{ category: EditCategory; count: number }>;
  urgencyDistribution: Array<{ level: UrgencyLevel; count: number }>;
  volumeByDay: Array<{ date: string; count: number }>;
  pendingCount: number;
  urgentCount: number;
  todayCount: number;
}
