import { Platform } from 'react-native';
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Consultation, AppNotification, AppointmentRequest, Appointment } from '../../types';
import { INITIAL_CONSULTATIONS, INITIAL_NOTIFICATIONS } from './mockData';

interface WorkflowState {
  consultations: Consultation[];
  notifications: AppNotification[];
  appointmentRequests: AppointmentRequest[];
  appointments: Appointment[];
  
  submitConsultation: (query: string, patientId: string, patientName: string, threadId?: string) => Promise<string>;
  sendFollowUpReply: (consultationId: string, replyContent: string) => Promise<void>;
  requestRescheduleAppointment: (appointmentId: string, requestedDate: string, requestedTime: string, reason: string) => Promise<string>;
  approveConsultation: (id: string, response: string) => void;
  rejectConsultation: (id: string, reason: string) => void;
  getConsultationById: (id: string) => Consultation | undefined;
  markNotificationRead: (id: string) => void;
  simulateDoctorReview: (id: string) => void;
}

const generateId = () => Math.random().toString(36).substring(2, 9);

export const useMockWorkflow = create<WorkflowState>()(
  persist(
    (set, get) => ({
      consultations: INITIAL_CONSULTATIONS,
      notifications: INITIAL_NOTIFICATIONS,
      appointmentRequests: [
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
        }
      ],
      appointments: [
        { id: 'a1', patientId: 'hero-001', doctorName: 'Dr. Amelia Smith', date: '2023-10-15', time: '10:00 AM', reason: 'Follow-up Checkup', status: 'confirmed' },
        { id: 'a2', patientId: 'hero-001', doctorName: 'Dr. Amelia Smith', date: '2023-02-20', time: '02:30 PM', reason: 'Routine Checkup', status: 'completed' }
      ],
      
      submitConsultation: async (query, patientId, patientName, threadId) => {
        // MODULE 1: Multi-turn threading! If threadId provided, append to existing thread
        if (threadId) {
          await get().sendFollowUpReply(threadId, query);
          return threadId;
        }

        const id = 'cons-' + generateId();
        const newCons: Consultation = {
          id,
          patientId,
          patientName,
          query,
          status: 'sending',
          threadStatus: 'awaiting_doctor',
          turnCount: 1,
          messages: [
            { id: 'msg-' + generateId(), consultationId: id, role: 'patient', content: query, timestamp: new Date().toISOString(), status: 'sending' }
          ],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString()
        };
        
        set((state) => ({
          consultations: [newCons, ...state.consultations]
        }));
        
        // Notify cross-tab
        if (Platform.OS === 'web' && typeof window !== 'undefined' && typeof BroadcastChannel !== 'undefined') {
          try {
            const bc = new BroadcastChannel('carepilot_workflow_channel');
            bc.postMessage({ type: 'NEW_CONSULTATION', id });
            bc.close();
          } catch (_e) {}
        }

        // Simulate sending -> processing -> doctor_review
        setTimeout(() => {
          set((state) => ({
            consultations: state.consultations.map(c => 
              c.id === id ? { 
                ...c, 
                status: 'processing', 
                messages: c.messages.map(m => m.role === 'patient' ? { ...m, status: 'processing' } : m)
              } : c
            )
          }));
          
          setTimeout(() => {
            get().simulateDoctorReview(id);
          }, 2000);
        }, 1000);
        
        return id;
      },

      sendFollowUpReply: async (consultationId, replyContent) => {
        // MODULE 1: Follow-up reply re-enters same thread
        const newMsgId = 'msg-' + generateId();
        set((state) => ({
          consultations: state.consultations.map(c => {
            if (c.id === consultationId) {
              const newMsg = {
                id: newMsgId,
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

        if (Platform.OS === 'web' && typeof window !== 'undefined' && typeof BroadcastChannel !== 'undefined') {
          try {
            const bc = new BroadcastChannel('carepilot_workflow_channel');
            bc.postMessage({ type: 'THREAD_REPLY', consultationId });
            bc.close();
          } catch (_e) {}
        }
      },

      requestRescheduleAppointment: async (appointmentId, requestedDate, requestedTime, reason) => {
        // MODULE 2: Reschedule request flow (routes to doctor for approval — HITL pattern)
        const reqId = 'req-' + generateId();
        const appt = get().appointments.find(a => a.id === appointmentId);
        
        const newReq: AppointmentRequest = {
          id: reqId,
          patientId: appt ? appt.patientId : 'hero-001',
          patientName: 'Christian Labadie',
          requestType: 'reschedule',
          originalAppointmentId: appointmentId,
          requestedDate,
          requestedTime,
          reason,
          status: 'pending_doctor_approval',
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString()
        };

        set((state) => ({
          appointmentRequests: [newReq, ...state.appointmentRequests],
          appointments: state.appointments.map(a => a.id === appointmentId ? { ...a, status: 'pending' as const } : a)
        }));

        if (Platform.OS === 'web' && typeof window !== 'undefined' && typeof BroadcastChannel !== 'undefined') {
          try {
            const bc = new BroadcastChannel('carepilot_workflow_channel');
            bc.postMessage({ type: 'RESCHEDULE_REQUEST', reqId });
            bc.close();
          } catch (_e) {}
        }

        return reqId;
      },
      
      simulateDoctorReview: (id) => {
        set((state) => ({
          consultations: state.consultations.map(c => 
            c.id === id ? { 
              ...c, 
              status: 'doctor_review',
              threadStatus: 'awaiting_doctor',
              messages: c.messages.map(m => m.role === 'patient' ? { ...m, status: 'doctor_review' } : m)
            } : c
          )
        }));
      },
      
      approveConsultation: (id, response) => {
        // MODULE 4: Patient in-app notification fires ONLY when doctor approves (never on raw AI draft!)
        set((state) => {
          const cons = state.consultations.find(c => c.id === id);
          if (!cons) return state;
          
          const updatedCons = {
            ...cons,
            status: 'approved' as const,
            threadStatus: 'approved' as const,
            finalResponse: response,
            messages: [
              ...cons.messages.map(m => m.role === 'patient' ? { ...m, status: 'approved' as const } : m),
              { id: 'msg-' + generateId(), consultationId: id, role: 'doctor' as const, content: response, timestamp: new Date().toISOString(), status: 'approved' as const }
            ],
            updatedAt: new Date().toISOString()
          };
          
          /* IN-APP NOTIFICATION ONLY (Expo Push / Web Push noted as future work candidate) */
          const notif: AppNotification = {
            id: 'notif-' + generateId(),
            userId: cons.patientId,
            category: 'consultation',
            title: 'Doctor Approved Response Available',
            body: 'Dr. Amelia Smith has reviewed and approved your consultation.',
            read: false,
            relatedId: id,
            createdAt: new Date().toISOString()
          };
          
          return {
            consultations: state.consultations.map(c => c.id === id ? updatedCons : c),
            notifications: [notif, ...state.notifications]
          };
        });
      },
      
      rejectConsultation: (id, _reason) => {
         set((state) => {
            return {
               consultations: state.consultations.map(c => c.id === id ? { ...c, status: 'rejected' } : c)
            }
         });
      },
      
      getConsultationById: (id) => {
        return get().consultations.find(c => c.id === id);
      },
      
      markNotificationRead: (id) => {
        set((state) => ({
          notifications: state.notifications.map(n => n.id === id ? { ...n, read: true } : n)
        }));
      }
    }),
    {
      name: 'carepilot:workflow',
      storage: createJSONStorage(() => AsyncStorage)
    }
  )
);

// Cross-tab sync setup on web environment
if (Platform.OS === 'web' && typeof window !== 'undefined') {
  const syncStoreFromStorage = () => {
    try {
      useMockWorkflow.persist.rehydrate();
    } catch (_e) {}
  };

  try {
    if (typeof BroadcastChannel !== 'undefined') {
      const bc = new BroadcastChannel('carepilot_workflow_channel');
      bc.onmessage = () => {
        syncStoreFromStorage();
      };
    }
  } catch (_e) {}

  if (typeof window.addEventListener === 'function') {
    window.addEventListener('storage', (e) => {
      if (e.key === 'carepilot:workflow') {
        syncStoreFromStorage();
      }
    });
  }

  setInterval(() => {
    syncStoreFromStorage();
  }, 1500);
}
