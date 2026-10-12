import { Consultation, Patient, AppNotification, Appointment, TimelineEvent, Document, AppointmentRequest } from '../../types';

export const mockPatients: Patient[] = [
  {
    id: 'hero-001',
    firstName: 'Christian',
    lastName: 'Labadie',
    dateOfBirth: '1945-05-12',
    gender: 'M',
    age: 81,
    conditions: [
      { id: 'c1', description: 'CKD Stage 3', startDate: '2020-01-01', active: true },
      { id: 'c2', description: 'Hypertension', startDate: '2015-06-15', active: true },
      { id: 'c3', description: 'Type 2 Diabetes', startDate: '2010-03-10', active: true },
    ],
    medications: [
      { id: 'm1', patientId: 'hero-001', name: 'Lisinopril', dosage: '10mg', frequency: 'Daily', startDate: '2020-01-01', active: true },
      { id: 'm2', patientId: 'hero-001', name: 'Metformin', dosage: '500mg', frequency: 'Twice daily', startDate: '2010-03-10', active: true },
      { id: 'm3', patientId: 'hero-001', name: 'Furosemide', dosage: '40mg', frequency: 'Daily', startDate: '2021-05-20', active: true },
      { id: 'm4', patientId: 'hero-001', name: 'Amlodipine', dosage: '5mg', frequency: 'Daily', startDate: '2015-06-15', stopDate: '2020-01-01', active: false },
      { id: 'm5', patientId: 'hero-001', name: 'Ibuprofen', dosage: '400mg', frequency: 'As needed', startDate: '2021-01-01', stopDate: '2021-02-01', active: false },
    ],
    allergies: [],
    lastConsultation: '2023-08-15',
    pendingConsultationCount: 1,
  },
  {
    id: 'p2',
    firstName: 'James',
    lastName: 'Okonkwo',
    dateOfBirth: '1959-08-22',
    gender: 'M',
    age: 67,
    conditions: [{ id: 'c4', description: 'Asthma', startDate: '2005-02-14', active: true }],
    medications: [],
    allergies: [],
    lastConsultation: '2023-09-01',
    pendingConsultationCount: 1,
  },
  {
    id: 'p3',
    firstName: 'David',
    lastName: 'Chen',
    dateOfBirth: '1968-11-05',
    gender: 'M',
    age: 58,
    conditions: [],
    medications: [],
    allergies: [],
    lastConsultation: '2023-09-10',
    pendingConsultationCount: 1,
  },
  {
    id: 'p4',
    firstName: 'Sarah',
    lastName: 'Mitchell',
    dateOfBirth: '1992-04-18',
    gender: 'F',
    age: 34,
    conditions: [],
    medications: [],
    allergies: [],
    lastConsultation: '2023-09-14',
    pendingConsultationCount: 0,
  },
  {
    id: 'p5',
    firstName: 'Maria',
    lastName: 'Santos',
    dateOfBirth: '1954-07-30',
    gender: 'F',
    age: 72,
    conditions: [{ id: 'c5', description: 'Osteoporosis', startDate: '2018-09-11', active: true }],
    medications: [],
    allergies: [],
    lastConsultation: '2023-09-15',
    pendingConsultationCount: 0,
  },
  {
    id: 'p6',
    firstName: 'Robert',
    lastName: 'Johnson',
    dateOfBirth: '1980-12-02',
    gender: 'M',
    age: 45,
    conditions: [],
    medications: [],
    allergies: [],
    lastConsultation: '2023-08-20',
    pendingConsultationCount: 0,
  }
];

export const mockConsultations: Consultation[] = [
  {
    id: 'consult-001',
    patientId: 'hero-001',
    patientName: 'Christian Labadie',
    patientAge: 81,
    patientGender: 'M',
    query: 'Why is my recent blood test different from before?',
    status: 'doctor_review',
    threadStatus: 'patient_replied',
    turnCount: 2,
    intent: 'report_query',
    urgency: 'soon',
    aiAnalysis: {
      intent: 'report_query',
      urgency: 'soon',
      urgencyScore: 75,
      patientContextRetrieved: true,
      knowledgeContextRetrieved: true
    },
    aiDraft: {
      content: 'Your recent creatinine level has increased from 1.2 to 1.4 mg/dL, which suggests a decline in kidney filtering function. Your eGFR has also decreased from 51 to 47 mL/min/1.73m2. While this change warrants attention, it does not require emergency care at this time. I recommend scheduling a follow-up appointment to discuss adjustments to your management plan.',
      generatedAt: new Date().toISOString(),
      citations: [
        { id: 'cit-1', title: 'Creatinine Blood Test', source: 'MedlinePlus', sourceType: 'Patient Education', url: 'https://medlineplus.gov/lab-tests/creatinine-test/', excerpt: 'Serum creatinine levels reflect renal clearance...' },
        { id: 'cit-2', title: 'Chronic Kidney Disease Stages', source: 'NIDDK', sourceType: 'Clinical Guide', url: 'https://www.niddk.nih.gov', excerpt: 'Stage 3 CKD indicates eGFR 30-59 mL/min...' }
      ]
    },
    messages: [
      {
        id: 'msg-1',
        consultationId: 'consult-001',
        role: 'patient',
        content: 'Why is my recent blood test different from before?',
        timestamp: '2023-08-15T09:00:00Z',
        status: 'approved'
      },
      {
        id: 'msg-2',
        consultationId: 'consult-001',
        role: 'doctor',
        content: 'Your creatinine level increased from 1.2 to 1.4 mg/dL. This is consistent with Stage 3 CKD progression.',
        timestamp: '2023-08-15T10:30:00Z',
        status: 'approved'
      },
      {
        id: 'msg-3',
        consultationId: 'consult-001',
        role: 'patient',
        content: 'Should I adjust my Metformin dosage or stop taking Ibuprofen because of this?',
        timestamp: '2023-08-15T11:15:00Z',
        status: 'doctor_review'
      }
    ],
    createdAt: '2023-08-15T09:00:00Z',
    updatedAt: new Date().toISOString(),
  },
  {
    id: 'consult-002',
    patientId: 'p2',
    patientName: 'James Okonkwo',
    query: 'chest tightness and shortness of breath',
    status: 'doctor_review',
    threadStatus: 'awaiting_doctor',
    turnCount: 1,
    intent: 'symptom_query',
    urgency: 'urgent',
    isHighPriorityAlert: true,
    isRedFlagOverride: true,
    alertReason: 'RED-FLAG OVERRIDE: Acute Chest Tightness & High Urgency Score',
    aiAnalysis: {
      intent: 'symptom_query',
      urgency: 'urgent',
      urgencyScore: 95,
      patientContextRetrieved: true,
      knowledgeContextRetrieved: true,
      isHighPriorityAlert: true,
      isRedFlagOverride: true,
      alertReason: 'RED-FLAG OVERRIDE: Acute Chest Tightness'
    },
    aiDraft: {
      content: 'CRITICAL ALERT DRAFT: The patient reports acute chest tightness and shortness of breath. Based on clinical protocol, chest tightness requires immediate in-person evaluation to rule out acute coronary syndrome or pulmonary complications. Advice: Instruct patient to seek immediate emergency medical care (call 911 or go to nearest ER). Do not delay evaluation.',
      generatedAt: new Date().toISOString(),
      citations: [
        { id: 'cit-j1', title: 'Evaluation of Acute Chest Pain', source: 'AHA/ACC Clinical Guidelines', sourceType: 'Clinical Protocol', url: 'https://www.heart.org', excerpt: 'New onset chest tightness with dyspnea warrants immediate emergency assessment.' }
      ]
    },
    messages: [
      {
        id: 'msg-002-1',
        consultationId: 'consult-002',
        role: 'patient',
        content: 'I am experiencing sudden chest tightness and shortness of breath since this morning.',
        timestamp: new Date().toISOString(),
        status: 'doctor_review'
      }
    ],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
  {
    id: 'consult-003',
    patientId: 'p3',
    patientName: 'David Chen',
    query: 'medication side effects',
    status: 'doctor_review',
    threadStatus: 'awaiting_doctor',
    turnCount: 1,
    intent: 'medication_query',
    urgency: 'soon',
    aiAnalysis: {
      intent: 'medication_query',
      urgency: 'soon',
      urgencyScore: 60,
      patientContextRetrieved: true,
      knowledgeContextRetrieved: true
    },
    aiDraft: {
      content: 'The patient reports feeling dizzy after taking a new medication dose. Dizziness can occur when initiating antihypertensive or glycemic control agents due to blood pressure or blood glucose fluctuations. Recommendation: Advise patient to measure blood pressure and heart rate when symptomatic, avoid sudden posture changes, and schedule a follow-up review for potential dosage titration.',
      generatedAt: new Date().toISOString(),
      citations: [
        { id: 'cit-d1', title: 'Managing Antihypertensive Side Effects', source: 'MedlinePlus', sourceType: 'Patient Safety Guide', url: 'https://medlineplus.gov', excerpt: 'Postural hypotension and dizziness during medication initiation...' }
      ]
    },
    messages: [
      {
        id: 'msg-003-1',
        consultationId: 'consult-003',
        role: 'patient',
        content: 'Feeling dizzy after taking new medication dose.',
        timestamp: new Date().toISOString(),
        status: 'doctor_review'
      }
    ],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  }
];

export const mockAppointmentRequests: AppointmentRequest[] = [
  {
    id: 'req-001',
    patientId: 'hero-001',
    patientName: 'Christian Labadie',
    requestType: 'reschedule',
    originalAppointmentId: 'a1',
    requestedDate: '2023-10-22',
    requestedTime: '11:00 AM',
    reason: 'Conflict with lab blood draw appointment on original date',
    status: 'pending_doctor_approval',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  },
  {
    id: 'req-002',
    patientId: 'p3',
    patientName: 'David Chen',
    requestType: 'new',
    requestedDate: '2023-10-18',
    requestedTime: '02:00 PM',
    reason: 'Follow-up consultation for medication side effects',
    status: 'pending_doctor_approval',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  },
  {
    id: 'req-003',
    patientId: 'p4',
    patientName: 'Sarah Mitchell',
    requestType: 'new',
    requestedDate: '2023-10-20',
    requestedTime: '10:30 AM',
    reason: 'Routine anxiety & medication review consultation',
    status: 'pending_doctor_approval',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  },
  {
    id: 'req-004',
    patientId: 'p2',
    patientName: 'James Okonkwo',
    requestType: 'reschedule',
    originalAppointmentId: 'a3',
    requestedDate: '2023-10-21',
    requestedTime: '09:30 AM',
    reason: 'Post-cardiac follow-up schedule adjustment',
    status: 'pending_doctor_approval',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  }
];

export const mockTimelineEvents: TimelineEvent[] = [
  { id: 't1', patientId: 'hero-001', type: 'consultation', date: '2023-08-15', title: 'Consultation Request', description: 'Patient asked about lab results.' },
  { id: 't2', patientId: 'hero-001', type: 'lab', date: '2023-08-10', title: 'Lab Results', description: 'Comprehensive Metabolic Panel completed.' },
  { id: 't3', patientId: 'hero-001', type: 'encounter', date: '2023-02-20', title: 'Clinic Visit', description: 'Routine checkup.' },
  { id: 't4', patientId: 'hero-001', type: 'lab', date: '2023-02-14', title: 'Lab Results', description: 'Routine blood work.' },
  { id: 't5', patientId: 'hero-001', type: 'prescription', date: '2022-11-20', title: 'Prescription Refill', description: 'Metformin refilled.' },
  { id: 't6', patientId: 'hero-001', type: 'consultation', date: '2022-11-20', title: 'Consultation Request', description: 'Requested refill.' },
  { id: 't7', patientId: 'hero-001', type: 'lab', date: '2022-09-20', title: 'Lab Results', description: 'Routine blood work.' },
  { id: 't8', patientId: 'hero-001', type: 'encounter', date: '2022-03-20', title: 'Clinic Visit', description: 'Initial consultation.' },
];

export const mockDocuments: Document[] = [
  { id: 'd1', patientId: 'hero-001', name: 'Comprehensive Metabolic Panel', category: 'lab_report', uploadedAt: '2023-08-12', size: '1.2 MB' },
  { id: 'd2', patientId: 'hero-001', name: 'Prescription Detail', category: 'prescription', uploadedAt: '2023-06-15', size: '450 KB' },
];

export const mockAppointments: Appointment[] = [
  { id: 'a1', patientId: 'hero-001', patientName: 'Christian Labadie', doctorName: 'Dr. Amelia Smith', date: '2023-10-15', time: '10:00 AM', reason: 'Follow-up Nephrology Checkup', status: 'confirmed' },
  { id: 'a2', patientId: 'hero-001', patientName: 'Christian Labadie', doctorName: 'Dr. Amelia Smith', date: '2023-02-20', time: '02:30 PM', reason: 'Routine Kidney Function Checkup', status: 'completed' },
  { id: 'a3', patientId: 'p2', patientName: 'James Okonkwo', doctorName: 'Dr. Amelia Smith', date: new Date().toISOString().split('T')[0], time: '11:00 AM', reason: 'Chest tightness & dyspnea evaluation', status: 'confirmed' },
  { id: 'a4', patientId: 'p3', patientName: 'David Chen', doctorName: 'Dr. Amelia Smith', date: new Date().toISOString().split('T')[0], time: '03:00 PM', reason: 'Medication side effects review', status: 'confirmed' },
  { id: 'a5', patientId: 'p4', patientName: 'Sarah Mitchell', doctorName: 'Dr. Amelia Smith', date: '2023-10-20', time: '09:00 AM', reason: 'Annual physical examination', status: 'confirmed' },
  { id: 'a6', patientId: 'p5', patientName: 'Maria Santos', doctorName: 'Dr. Amelia Smith', date: '2023-09-01', time: '01:00 PM', reason: 'Bone density scan follow-up', status: 'completed' },
  { id: 'a7', patientId: 'p6', patientName: 'Robert Johnson', doctorName: 'Dr. Amelia Smith', date: '2023-08-20', time: '11:30 AM', reason: 'Routine hypertension follow-up', status: 'completed' },
  { id: 'a8', patientId: 'p5', patientName: 'Maria Santos', doctorName: 'Dr. Amelia Smith', date: '2023-10-25', time: '01:30 PM', reason: 'Osteoporosis management review', status: 'confirmed' },
  { id: 'a9', patientId: 'p6', patientName: 'Robert Johnson', doctorName: 'Dr. Amelia Smith', date: '2023-10-28', time: '11:00 AM', reason: 'Quarterly cardiovascular review', status: 'confirmed' },
];

export const mockNotifications: AppNotification[] = [
  { id: 'n1', userId: 'doc-001', category: 'consultation', title: 'HIGH PRIORITY RED-FLAG ALERT', body: 'James Okonkwo reported acute chest tightness and shortness of breath.', read: false, createdAt: new Date().toISOString(), relatedId: 'consult-002' },
  { id: 'n2', userId: 'doc-001', category: 'appointment', title: 'Reschedule Request Pending', body: 'Christian Labadie requested to reschedule appointment a1 to Oct 22.', read: false, createdAt: new Date().toISOString(), relatedId: 'req-001' },
  { id: 'n3', userId: 'doc-001', category: 'consultation', title: 'Follow-Up Reply Received', body: 'Christian Labadie replied to consultation consult-001.', read: true, createdAt: '2023-09-15T08:00:00Z', relatedId: 'consult-001' },
];
