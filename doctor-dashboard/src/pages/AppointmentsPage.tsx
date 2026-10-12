import { useState } from 'react';
import { useWorkflowStore } from '../services/mock/mockWorkflow';
import { cn } from '../utils/cn';
import { Calendar, Clock, Check, RefreshCw, Send } from 'lucide-react';
import { Dialog } from '@headlessui/react';
import toast from 'react-hot-toast';

export function AppointmentsPage() {
  const appointments = useWorkflowStore(state => state.appointments);
  const appointmentRequests = useWorkflowStore(state => state.appointmentRequests);
  const respondAppointmentRequest = useWorkflowStore(state => state.respondAppointmentRequest);

  const [activeTab, setActiveTab] = useState<'requests' | 'today' | 'upcoming' | 'past'>('requests');
  const [selectedReqId, setSelectedReqId] = useState<string | null>(null);
  const [isAltModalOpen, setIsAltModalOpen] = useState(false);
  const [altDate, setAltDate] = useState('2023-10-24');
  const [altTime, setAltTime] = useState('02:00 PM');
  const [altNote, setAltNote] = useState('');

  const pendingRequests = appointmentRequests.filter(r => r.status === 'pending_doctor_approval');
  const todayStr = new Date().toISOString().split('T')[0];

  const filteredAppointments = appointments.filter(a => {
    if (activeTab === 'today') return a.date === todayStr;
    if (activeTab === 'upcoming') return a.date >= todayStr && a.status !== 'completed' && a.status !== 'cancelled';
    if (activeTab === 'past') return a.date < todayStr || a.status === 'completed' || a.status === 'cancelled';
    return false;
  }).sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time));

  const handleApproveRequest = (reqId: string) => {
    respondAppointmentRequest(reqId, 'approve');
    toast.success('Appointment request approved & confirmed!');
  };

  const handleDenyRequest = (reqId: string) => {
    respondAppointmentRequest(reqId, 'deny', 'Denied due to doctor schedule conflict.');
    toast.error('Appointment request denied.');
  };

  const handleOpenProposeAlt = (reqId: string) => {
    setSelectedReqId(reqId);
    setIsAltModalOpen(true);
  };

  const handleSubmitAltPropose = () => {
    if (!selectedReqId) return;
    respondAppointmentRequest(selectedReqId, 'propose_alternative', altNote || 'Proposed alternative schedule.', altDate, altTime);
    toast.success('Alternative appointment time proposed to patient.');
    setIsAltModalOpen(false);
    setAltNote('');
  };

  const tabs = [
    { id: 'requests', label: `Pending Requests (${pendingRequests.length})` },
    { id: 'today', label: 'Today' },
    { id: 'upcoming', label: 'Upcoming' },
    { id: 'past', label: 'Past' }
  ] as const;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-text-navy">Appointments & Scheduling</h1>
          <p className="text-sm text-text-muted">Manage patient requests, reschedules & upcoming visits</p>
        </div>
      </div>

      <div className="flex space-x-4 border-b border-border-subtle">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 transition-colors relative",
              activeTab === tab.id ? "border-primary text-primary font-bold" : "border-transparent text-text-muted hover:text-text-navy hover:border-border-subtle"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* MODULE 2: Pending Requests & Reschedules Queue */}
      {activeTab === 'requests' && (
        <div className="space-y-4">
          {pendingRequests.length === 0 ? (
            <div className="p-12 text-center bg-white rounded-lg border border-border-subtle text-text-muted">
              No pending appointment or reschedule requests awaiting approval.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {pendingRequests.map(req => (
                <div key={req.id} className="bg-white p-5 rounded-lg border-2 border-warning/40 shadow-sm flex flex-col justify-between">
                  <div>
                    <div className="flex justify-between items-start mb-3">
                      <div>
                        <span className="font-bold text-text-navy text-lg">{req.patientName}</span>
                        <span className="block text-xs font-mono text-text-muted">Patient ID: {req.patientId}</span>
                      </div>
                      <span className={cn(
                        "px-2.5 py-0.5 rounded-full text-xs font-bold uppercase",
                        req.requestType === 'reschedule' ? "bg-purple-100 text-purple-700" : "bg-yellow-100 text-warning"
                      )}>
                        {req.requestType === 'reschedule' ? 'Reschedule Request' : 'New Request'}
                      </span>
                    </div>

                    <div className="space-y-2 mb-4 bg-gray-50 p-3 rounded-md text-xs border border-border-subtle">
                      <div className="flex items-center text-text-navy">
                        <Calendar className="w-3.5 h-3.5 mr-2 text-primary" />
                        <span className="font-semibold">Requested:</span>
                        <span className="ml-1 text-primary font-bold">{req.requestedDate} at {req.requestedTime}</span>
                      </div>
                      <div className="text-text-muted">
                        <span className="font-semibold text-text-navy">Reason:</span> {req.reason}
                      </div>
                    </div>
                  </div>

                  {/* Doctor Actions: Approve / Deny / Propose Alternative */}
                  <div className="pt-3 border-t border-border-subtle flex flex-wrap gap-2 justify-end">
                    <button 
                      onClick={() => handleDenyRequest(req.id)}
                      className="px-3 py-1.5 text-xs text-urgent border border-urgent rounded hover:bg-red-50 font-medium"
                    >
                      Deny
                    </button>
                    <button 
                      onClick={() => handleOpenProposeAlt(req.id)}
                      className="px-3 py-1.5 text-xs text-text-navy bg-gray-100 rounded hover:bg-gray-200 font-medium flex items-center"
                    >
                      <RefreshCw className="w-3 h-3 mr-1" /> Propose Alternative
                    </button>
                    <button 
                      onClick={() => handleApproveRequest(req.id)}
                      className="px-3 py-1.5 text-xs bg-primary text-white rounded hover:bg-blue-700 font-medium flex items-center"
                    >
                      <Check className="w-3 h-3 mr-1" /> Approve Request
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Scheduled Appointments Tabs */}
      {activeTab !== 'requests' && (
        <div>
          {filteredAppointments.length === 0 ? (
            <div className="p-12 text-center bg-white rounded-lg border border-border-subtle text-text-muted">
              No {activeTab} appointments found.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredAppointments.map(a => (
                <div key={a.id} className="bg-white p-5 rounded-lg border border-border-subtle shadow-sm flex flex-col h-full">
                  <div className="flex justify-between items-start mb-4">
                    <div className="flex flex-col">
                      <span className="font-bold text-text-navy text-lg">{a.patientName}</span>
                      <span className="text-sm text-text-muted flex items-center mt-1">
                        <Calendar className="w-3.5 h-3.5 mr-1" /> {a.date}
                      </span>
                      <span className="text-sm text-text-muted flex items-center mt-1">
                        <Clock className="w-3.5 h-3.5 mr-1" /> {a.time}
                      </span>
                    </div>
                    <span className={cn(
                      "px-2.5 py-1 rounded-full text-xs font-medium uppercase",
                      a.status === 'confirmed' ? "bg-green-100 text-success" :
                      a.status === 'rescheduled' ? "bg-purple-100 text-purple-700" :
                      a.status === 'completed' ? "bg-gray-100 text-text-muted" : "bg-red-100 text-urgent"
                    )}>
                      {a.status}
                    </span>
                  </div>
                  
                  <div className="mb-4 flex-1">
                    <p className="text-sm text-text-navy"><span className="font-semibold">Reason:</span> {a.reason}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Propose Alternative Time Dialog */}
      <Dialog open={isAltModalOpen} onClose={() => setIsAltModalOpen(false)} className="relative z-50">
        <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
        <div className="fixed inset-0 flex w-screen items-center justify-center p-4">
          <Dialog.Panel className="mx-auto max-w-md rounded bg-white p-6 shadow-xl w-full space-y-4">
            <Dialog.Title className="text-lg font-bold text-text-navy flex items-center">
              <RefreshCw className="w-5 h-5 mr-2 text-primary" /> Propose Alternative Schedule
            </Dialog.Title>
            
            <div>
              <label className="block text-xs font-semibold text-text-navy mb-1">Alternative Date</label>
              <input 
                type="text" 
                value={altDate} 
                onChange={e => setAltDate(e.target.value)} 
                className="w-full border border-border-subtle rounded p-2 text-sm text-black"
                placeholder="YYYY-MM-DD" 
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-navy mb-1">Alternative Time</label>
              <input 
                type="text" 
                value={altTime} 
                onChange={e => setAltTime(e.target.value)} 
                className="w-full border border-border-subtle rounded p-2 text-sm text-black"
                placeholder="e.g. 02:00 PM" 
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-navy mb-1">Doctor Note to Patient</label>
              <textarea 
                value={altNote} 
                onChange={e => setAltNote(e.target.value)} 
                className="w-full border border-border-subtle rounded p-2 text-sm text-black"
                rows={3}
                placeholder="Explain why this alternative time is proposed..."
              />
            </div>

            <div className="flex justify-end space-x-3 pt-2">
              <button onClick={() => setIsAltModalOpen(false)} className="px-4 py-2 text-sm text-text-muted hover:bg-gray-100 rounded">Cancel</button>
              <button onClick={handleSubmitAltPropose} className="px-4 py-2 text-sm bg-primary text-white rounded hover:bg-blue-700 font-bold flex items-center">
                <Send className="w-4 h-4 mr-1.5" /> Send Proposal
              </button>
            </div>
          </Dialog.Panel>
        </div>
      </Dialog>
    </div>
  );
}
