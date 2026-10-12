import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { Consultation, AppNotification, EditCategory, Patient, Appointment, TimelineEvent, Document, AppointmentRequest } from '../../types';
import { mockConsultations, mockNotifications, mockPatients, mockAppointments, mockTimelineEvents, mockDocuments, mockAppointmentRequests } from './mockData';

interface WorkflowState {
  consultations: Consultation[];
  patients: Patient[];
  doctorNotifications: AppNotification[];
  appointments: Appointment[];
  appointmentRequests: AppointmentRequest[];
  timelineEvents: TimelineEvent[];
  documents: Document[];
  
  approveConsultation: (id: string, finalResponse: string, editCategory: EditCategory) => void;
  rejectConsultation: (id: string, reason: string, note?: string) => void;
  saveDraft: (id: string, draftContent: string) => void;
  respondAppointmentRequest: (requestId: string, action: 'approve' | 'deny' | 'propose_alternative', doctorResponse?: string, altDate?: string, altTime?: string) => void;
  sendFollowUpReply: (consultationId: string, replyContent: string) => void;
  getPendingQueue: () => Consultation[];
  getConsultationById: (id: string) => Consultation | undefined;
  getPatientById: (id: string) => Patient | undefined;
  markNotificationRead: (id: string) => void;
  markAllNotificationsRead: () => void;
}

const notifyCrossTabSync = () => {
  if (typeof window !== 'undefined') {
    try {
      const bc = new BroadcastChannel('carepilot_workflow_channel');
      bc.postMessage({ type: 'WORKFLOW_UPDATED', timestamp: Date.now() });
      bc.close();
    } catch (_e) {
      // Fallback
    }
    window.dispatchEvent(new Event('storage'));
  }
};

export const useWorkflowStore = create<WorkflowState>()(
  persist(
    (set, get) => ({
      consultations: mockConsultations,
      patients: mockPatients,
      doctorNotifications: mockNotifications,
      appointments: mockAppointments,
      appointmentRequests: mockAppointmentRequests,
      timelineEvents: mockTimelineEvents,
      documents: mockDocuments,
      
      approveConsultation: (id, finalResponse, editCategory) => {
        set((state) => {
          const updatedConsultations = state.consultations.map(c => 
            c.id === id 
              ? { 
                  ...c, 
                  status: 'approved' as const, 
                  threadStatus: 'approved' as const,
                  finalResponse, 
                  messages: [
                    ...(c.messages || [
                      { id: 'msg-p1', consultationId: id, role: 'patient' as const, content: c.query, timestamp: c.createdAt, status: 'approved' as const }
                    ]).map(m => ({ ...m, status: 'approved' as const })),
                    { 
                      id: 'msg-doc-' + Date.now(), 
                      consultationId: id, 
                      role: 'doctor' as const, 
                      content: finalResponse, 
                      timestamp: new Date().toISOString(), 
                      status: 'approved' as const 
                    }
                  ],
                  doctorReview: { 
                    doctorId: 'doc-001', 
                    doctorName: 'Dr. Amelia Smith', 
                    action: 'approved' as const, 
                    editCategory,
                    editedContent: finalResponse,
                    reviewedAt: new Date().toISOString() 
                  },
                  updatedAt: new Date().toISOString()
                } 
              : c
          );
          return { consultations: updatedConsultations };
        });
        notifyCrossTabSync();
      },
      
      rejectConsultation: (id, reason, note) => {
        set((state) => ({
          consultations: state.consultations.map(c => 
            c.id === id 
              ? { 
                  ...c, 
                  status: 'rejected' as const,
                  doctorReview: { 
                    doctorId: 'doc-001', 
                    doctorName: 'Dr. Amelia Smith', 
                    action: 'rejected' as const, 
                    reason: reason as any,
                    reasonNote: note,
                    reviewedAt: new Date().toISOString() 
                  },
                  updatedAt: new Date().toISOString()
                } 
              : c
          )
        }));
        notifyCrossTabSync();
      },

      saveDraft: (id, draftContent) => {
        set((state) => ({
          consultations: state.consultations.map(c => 
            c.id === id && c.aiDraft
              ? { 
                  ...c, 
                  aiDraft: { ...c.aiDraft, content: draftContent },
                  updatedAt: new Date().toISOString()
                } 
              : c
          )
        }));
        notifyCrossTabSync();
      },

      sendFollowUpReply: (consultationId, replyContent) => {
        set((state) => ({
          consultations: state.consultations.map(c => {
            if (c.id === consultationId) {
              const newMsg = {
                id: 'msg-' + Date.now(),
                consultationId,
                role: 'patient' as const,
                content: replyContent,
                timestamp: new Date().toISOString(),
                status: 'doctor_review' as const
              };
              return {
                ...c,
                status: 'doctor_review' as const,
                threadStatus: 'patient_replied' as const,
                turnCount: (c.turnCount || 1) + 1,
                messages: [...(c.messages || []), newMsg],
                updatedAt: new Date().toISOString()
              };
            }
            return c;
          })
        }));
        notifyCrossTabSync();
      },

      respondAppointmentRequest: (requestId, action, doctorResponse, altDate, altTime) => {
        set((state) => {
          const req = state.appointmentRequests.find(r => r.id === requestId);
          if (!req) return state;

          const statusMap = {
            approve: 'approved' as const,
            deny: 'denied' as const,
            propose_alternative: 'alternative_proposed' as const
          };

          const newStatus = statusMap[action];
          const updatedRequests = state.appointmentRequests.map(r => 
            r.id === requestId 
              ? { 
                  ...r, 
                  status: newStatus, 
                  doctorResponse, 
                  proposedAlternativeDate: altDate, 
                  proposedAlternativeTime: altTime,
                  updatedAt: new Date().toISOString() 
                }
              : r
          );

          let updatedAppointments = state.appointments;
          if (action === 'approve') {
            if (req.requestType === 'reschedule' && req.originalAppointmentId) {
              updatedAppointments = state.appointments.map(a => 
                a.id === req.originalAppointmentId 
                  ? { ...a, date: req.requestedDate, time: req.requestedTime, status: 'rescheduled' as const }
                  : a
              );
            } else {
              updatedAppointments = [
                ...state.appointments,
                {
                  id: 'app-' + Date.now(),
                  patientId: req.patientId,
                  patientName: req.patientName,
                  doctorName: 'Dr. Amelia Smith',
                  date: req.requestedDate,
                  time: req.requestedTime,
                  reason: req.reason,
                  status: 'confirmed' as const
                }
              ];
            }
          }

          return {
            appointmentRequests: updatedRequests,
            appointments: updatedAppointments
          };
        });
        notifyCrossTabSync();
      },

      getPendingQueue: () => {
        return get().consultations.filter(c => c.status === 'doctor_review');
      },

      getConsultationById: (id) => {
        return get().consultations.find(c => c.id === id) || mockConsultations.find(m => m.id === id);
      },

      getPatientById: (id) => {
        return get().patients.find(p => p.id === id) || mockPatients.find(m => m.id === id);
      },

      markNotificationRead: (id) => {
        set((state) => ({
          doctorNotifications: state.doctorNotifications.map(n => 
            n.id === id ? { ...n, read: true } : n
          )
        }));
      },

      markAllNotificationsRead: () => {
        set((state) => ({
          doctorNotifications: state.doctorNotifications.map(n => ({ ...n, read: true }))
        }));
      }
    }),
    { 
      name: 'carepilot:workflow:v4', 
      storage: createJSONStorage(() => localStorage) 
    }
  )
);
