import { useState, useEffect } from 'react';
import { useWorkflowStore } from '../services/mock/mockWorkflow';
import { useNavigate } from 'react-router-dom';
import { Search, AlertOctagon, Globe } from 'lucide-react';
import { UrgencyLevel, ConsultationStatus, Consultation } from '../types';
import { consultationApi } from '../services/api/consultationApi';

export function QueuePage() {
  const consultations = useWorkflowStore(state => state.consultations);
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const [urgencyFilter, setUrgencyFilter] = useState<UrgencyLevel | 'all'>('all');
  const [statusFilter, setStatusFilter] = useState<ConsultationStatus | 'all'>('doctor_review');
  const [backendQueue, setBackendQueue] = useState<Consultation[]>([]);

  useEffect(() => {
    let isMounted = true;
    const loadQueue = async () => {
      try {
        const items = await consultationApi.getQueue();
        if (!isMounted) return;
        const mapped: Consultation[] = items.map(r => ({
          id: r.id,
          patientId: r.patient_id,
          patientName: r.patient_id.includes('55dedab5') || r.patient_id === 'hero-001' ? 'Christian Labadie' : `Patient ${r.patient_id.slice(0, 8)}`,
          query: r.query_text,
          status: 'doctor_review',
          threadStatus: 'awaiting_doctor',
          intent: r.intent as any,
          language: r.language,
          urgency: r.urgency_final,
          validationStatus: r.validation_status,
          hasDraft: r.has_draft,
          isHighPriorityAlert: r.is_high_priority,
          isRedFlagOverride: r.is_red_flag_override,
          messages: [{ id: 'm1', consultationId: r.id, role: 'patient', content: r.query_text, timestamp: r.created_at }],
          createdAt: r.created_at,
          updatedAt: r.created_at,
        }));
        setBackendQueue(mapped);
      } catch (err) {
        // Fallback to local store silently if backend unreachable
      }
    };

    loadQueue();
    const interval = setInterval(loadQueue, 5000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const allItems = [
    ...backendQueue,
    ...consultations.filter(c => !backendQueue.some(b => b.id === c.id)),
  ];

  const highPriorityAlerts = allItems.filter(
    c => c.status === 'doctor_review' && (c.urgency === 'urgent' || c.isHighPriorityAlert || c.isRedFlagOverride)
  );

  const filtered = allItems.filter(c => {
    const matchesSearch = c.patientName.toLowerCase().includes(searchTerm.toLowerCase()) || 
                          c.query.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesUrgency = urgencyFilter === 'all' || c.urgency === urgencyFilter;
    const matchesStatus = statusFilter === 'all' || c.status === statusFilter;
    return matchesSearch && matchesUrgency && matchesStatus;
  }).sort((a, b) => {
    const weights: Record<string, number> = { urgent: 3, soon: 2, routine: 1 };
    return (weights[b.urgency || 'routine'] || 0) - (weights[a.urgency || 'routine'] || 0);
  });

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-text-navy">Review Queue</h1>
      </div>

      {/* MODULE 4: Visually Distinct High-Priority / Red-Flag Priority Alert Banner */}
      {highPriorityAlerts.length > 0 && (
        <div className="bg-red-50 border-2 border-red-500 rounded-lg p-4 flex items-start space-x-3 animate-pulse shadow-md">
          <div className="p-2 bg-red-100 text-urgent rounded-full shrink-0">
            <AlertOctagon className="w-6 h-6" />
          </div>
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold text-urgent uppercase tracking-wide flex items-center">
                High Priority Alert — Red-Flag Symptom Override Detected ({highPriorityAlerts.length})
              </h2>
              <span className="text-[10px] bg-urgent text-white px-2 py-0.5 rounded font-bold uppercase animate-bounce">
                IMMEDIATE ACTION
              </span>
            </div>
            <p className="text-xs text-text-navy mt-1">
              Urgency classifier & rule-based safety engine flagged critical clinical keywords:
            </p>
            <div className="mt-2 space-y-1">
              {highPriorityAlerts.map(a => (
                <div key={a.id} onClick={() => navigate(`/reviews/${a.id}`)} className="text-xs font-semibold text-urgent hover:underline cursor-pointer flex items-center">
                  • {a.patientName}: "{a.query}" ({a.alertReason || 'Acute symptom risk'})
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Search & Filter Options */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-text-muted h-5 w-5" />
          <input
            type="text"
            placeholder="Search patient or query..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10 w-full rounded-md border-border-subtle shadow-sm focus:border-primary focus:ring-primary text-black py-2 px-3 border"
          />
        </div>
        <select
          value={urgencyFilter}
          onChange={(e) => setUrgencyFilter(e.target.value as any)}
          className="rounded-md border-border-subtle shadow-sm focus:border-primary focus:ring-primary text-black py-2 px-3 border"
        >
          <option value="all">All Urgencies</option>
          <option value="urgent">Urgent</option>
          <option value="soon">Soon</option>
          <option value="routine">Routine</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as any)}
          className="rounded-md border-border-subtle shadow-sm focus:border-primary focus:ring-primary text-black py-2 px-3 border"
        >
          <option value="all">All Statuses</option>
          <option value="doctor_review">Pending Review</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
      </div>

      {/* Queue Table with Visually Distinct Red-Flag Styling */}
      <div className="bg-white shadow-sm rounded-lg border border-border-subtle overflow-hidden">
        {filtered.length === 0 ? (
          <div className="p-8 text-center text-text-muted">
            You're all caught up. No pending reviews.
          </div>
        ) : (
          <table className="min-w-full divide-y divide-border-subtle">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">Patient</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">Query / Thread</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">Lang</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">Urgency & Alerts</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-text-muted uppercase tracking-wider">Action</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-border-subtle">
              {filtered.map(c => {
                const isHigh = c.urgency === 'urgent' || c.isHighPriorityAlert || c.isRedFlagOverride;
                return (
                  <tr 
                    key={c.id} 
                    onClick={() => navigate(`/reviews/${c.id}`)} 
                    className={`hover:bg-gray-50 cursor-pointer transition-colors ${
                      isHigh ? 'bg-red-50/50 border-l-4 border-l-red-500 font-medium' : ''
                    }`}
                  >
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="font-bold text-text-navy flex items-center">
                        {c.patientName}
                        {isHigh && <AlertOctagon className="w-4 h-4 text-urgent ml-1.5 shrink-0" />}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-sm text-text-navy truncate max-w-xs">{c.query}</div>
                      {c.turnCount && c.turnCount > 1 && (
                        <span className="text-[10px] text-purple-700 font-bold bg-purple-100 px-1.5 py-0.5 rounded">
                          Multi-Turn Thread ({c.turnCount} turns)
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center space-x-1">
                        <Globe className="w-3 h-3 text-text-muted shrink-0" />
                        <span className="text-xs font-medium text-text-navy uppercase">{c.language || 'en'}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex flex-col items-start space-y-1">
                        <span className={`text-xs px-2.5 py-1 rounded-full font-bold ${
                          c.urgency === 'urgent' ? 'bg-red-100 text-urgent border border-urgent/30' :
                          c.urgency === 'soon' ? 'bg-yellow-100 text-warning border border-warning/30' :
                          'bg-blue-100 text-primary border border-primary/30'
                        }`}>
                          {c.urgency?.toUpperCase()}
                        </span>
                        {isHigh && (
                          <span className="text-[9px] font-bold text-urgent uppercase bg-red-100 px-1.5 py-0.5 rounded border border-red-200">
                            RED-FLAG OVERRIDE
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="text-xs px-2 py-1 bg-gray-100 rounded-full font-medium text-text-muted">
                        {c.threadStatus === 'patient_replied' ? 'Patient Replied' : c.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right">
                      <button className="text-primary hover:text-blue-700 font-bold text-sm">
                        Review
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
