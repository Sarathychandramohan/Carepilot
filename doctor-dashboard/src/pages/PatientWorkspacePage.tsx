import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useWorkflowStore } from '../services/mock/mockWorkflow';
import { cn } from '../utils/cn';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts';
import { FileText, Calendar, Activity, Clock, ChevronLeft, AlertTriangle, MessageSquare, ArrowRight, Pill, Stethoscope } from 'lucide-react';

export function PatientWorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const allPatients = useWorkflowStore(state => state.patients);
  const allTimelineEvents = useWorkflowStore(state => state.timelineEvents);
  const allDocuments = useWorkflowStore(state => state.documents);
  const allConsultations = useWorkflowStore(state => state.consultations);
  const allAppointments = useWorkflowStore(state => state.appointments);

  const patient = allPatients.find(p => p.id === id);
  const timelineEvents = allTimelineEvents.filter(e => e.patientId === id);
  const documents = allDocuments.filter(d => d.patientId === id);
  const consultations = allConsultations.filter(c => c.patientId === id);
  const appointments = allAppointments.filter(a => a.patientId === id);
  
  const [activeTab, setActiveTab] = useState('overview');

  // MODULE 3: Side-by-Side Lab Time Point Comparison state
  const labDataPoints = [
    { date: '2022-03-15', value: 1.1, egfr: 58 },
    { date: '2022-09-20', value: 1.2, egfr: 55 },
    { date: '2023-02-14', value: 1.3, egfr: 51 },
    { date: '2023-08-10', value: 1.4, egfr: 47 }
  ];

  const [pointAIdx, setPointAIdx] = useState(0); // Baseline
  const [pointBIdx, setPointBIdx] = useState(3); // Most recent

  if (!patient) {
    return (
      <div className="p-8 text-center">
        <h2 className="text-xl font-bold text-text-navy mb-2">Patient Not Found</h2>
        <p className="text-sm text-text-muted mb-4">The selected patient record could not be found.</p>
        <button onClick={() => navigate('/patients')} className="px-4 py-2 bg-primary text-white rounded-md text-sm font-bold">
          Back to Patient List
        </button>
      </div>
    );
  }

  const pointA = labDataPoints[pointAIdx];
  const pointB = labDataPoints[pointBIdx];
  const absDelta = (pointB.value - pointA.value).toFixed(2);
  const pctDelta = (((pointB.value - pointA.value) / pointA.value) * 100).toFixed(1);
  const pendingConsult = consultations.find(c => c.status === 'doctor_review');

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'timeline', label: 'Timeline' },
    { id: 'labs', label: 'Labs & Report Analysis' },
    { id: 'medications', label: 'Medications' },
    { id: 'documents', label: 'Documents' },
    { id: 'consultations', label: 'Consultations' },
    { id: 'appointments', label: 'Appointments' }
  ];

  return (
    <div className="space-y-6">
      {/* 1. Patient Header — Always Visible */}
      <div className="bg-white p-6 rounded-xl shadow-sm border border-border-subtle">
        <div className="flex items-center space-x-3 mb-4">
          <button onClick={() => navigate('/patients')} className="text-text-muted hover:text-text-navy text-sm font-semibold flex items-center">
            <ChevronLeft className="w-4 h-4 mr-1" /> Patients
          </button>
        </div>

        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div className="flex items-center space-x-4">
            <div className="w-14 h-14 bg-primary/10 rounded-full flex items-center justify-center text-primary font-bold text-xl border border-primary/20">
              {patient.firstName[0]}{patient.lastName[0]}
            </div>
            <div>
              <div className="flex items-center space-x-3">
                <h1 className="text-2xl font-bold text-text-navy">{patient.firstName} {patient.lastName}</h1>
                <span className="text-xs bg-gray-100 text-text-navy font-mono px-2.5 py-0.5 rounded border border-border-subtle font-semibold">
                  Patient ID: {patient.id}
                </span>
              </div>
              <p className="text-sm text-text-muted mt-0.5">
                {patient.gender === 'M' ? 'Male' : 'Female'} • DOB: {patient.dateOfBirth} ({patient.age}y) • Needham, Massachusetts
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {pendingConsult && (
              <button 
                onClick={() => navigate(`/reviews/${pendingConsult.id}`)}
                className="px-3.5 py-2 bg-urgent text-white rounded-lg text-xs font-bold hover:bg-red-700 transition-colors flex items-center shadow-sm"
              >
                <MessageSquare className="w-3.5 h-3.5 mr-1.5" /> New Review Pending
              </button>
            )}
            <button 
              onClick={() => setActiveTab('consultations')}
              className="px-3.5 py-2 bg-white border border-primary text-primary hover:bg-blue-50 rounded-lg text-xs font-bold transition-colors flex items-center"
            >
              <MessageSquare className="w-3.5 h-3.5 mr-1.5" /> View Conversation
            </button>
            <button 
              onClick={() => setActiveTab('timeline')}
              className="px-3.5 py-2 bg-gray-100 text-text-navy hover:bg-gray-200 rounded-lg text-xs font-bold transition-colors flex items-center"
            >
              <Clock className="w-3.5 h-3.5 mr-1.5" /> Patient History
            </button>
          </div>
        </div>

        {/* 2. Patient Summary KPI Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-6 border-t border-border-subtle">
          <div className="bg-gray-50/70 p-3 rounded-lg border border-border-subtle text-center">
            <span className="text-xs font-semibold text-text-muted uppercase">Conditions</span>
            <p className="text-xl font-bold text-text-navy mt-1">{patient.conditions.length}</p>
          </div>
          <div className="bg-gray-50/70 p-3 rounded-lg border border-border-subtle text-center">
            <span className="text-xs font-semibold text-text-muted uppercase">Medications</span>
            <p className="text-xl font-bold text-text-navy mt-1">{patient.medications.length}</p>
          </div>
          <div className="bg-gray-50/70 p-3 rounded-lg border border-border-subtle text-center">
            <span className="text-xs font-semibold text-text-muted uppercase">Lab Results</span>
            <p className="text-xl font-bold text-text-navy mt-1">4,306</p>
          </div>
          <div className="bg-gray-50/70 p-3 rounded-lg border border-border-subtle text-center">
            <span className="text-xs font-semibold text-text-muted uppercase">Encounters</span>
            <p className="text-xl font-bold text-text-navy mt-1">196</p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="mt-6 flex space-x-1 border-b border-border-subtle overflow-x-auto">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap",
                activeTab === tab.id ? "border-primary text-primary font-bold" : "border-transparent text-text-muted hover:text-text-navy hover:border-border-subtle"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Main Tab Content */}
      <div className="bg-white p-6 rounded-xl shadow-sm border border-border-subtle min-h-[450px]">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* 3. Documented Conditions & Current Medications */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Conditions Card */}
              <div className="bg-white border border-border-subtle rounded-xl p-5 shadow-sm">
                <div className="flex justify-between items-center mb-3">
                  <h3 className="text-base font-bold text-text-navy flex items-center">
                    <Stethoscope className="w-4 h-4 mr-2 text-primary" /> Documented Conditions
                  </h3>
                  <span className="text-[10px] bg-blue-50 text-primary font-bold px-2 py-0.5 rounded border border-primary/20">
                    Record Documented
                  </span>
                </div>
                <p className="text-xs text-text-muted mb-4">Documented active conditions in Synthea EMR record</p>
                
                <div className="space-y-2">
                  {patient.conditions.map(c => (
                    <div key={c.id} className="p-3 bg-gray-50 rounded-lg border border-border-subtle flex justify-between items-center">
                      <div>
                        <span className="text-sm font-bold text-text-navy">{c.description}</span>
                        <p className="text-xs text-text-muted mt-0.5">Diagnosed / Onset: {c.startDate}</p>
                      </div>
                      <span className="text-[10px] font-bold bg-green-100 text-success px-2 py-0.5 rounded uppercase">
                        Documented
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Medications Card */}
              <div className="bg-white border border-border-subtle rounded-xl p-5 shadow-sm">
                <div className="flex justify-between items-center mb-3">
                  <h3 className="text-base font-bold text-text-navy flex items-center">
                    <Pill className="w-4 h-4 mr-2 text-primary" /> Current Medications
                  </h3>
                  <button onClick={() => setActiveTab('medications')} className="text-xs text-primary font-bold hover:underline">
                    View Prescriptions
                  </button>
                </div>
                <p className="text-xs text-text-muted mb-4">Active prescribed medications & dosing regimens</p>

                <div className="space-y-2">
                  {patient.medications.filter(m => m.active).map(m => (
                    <div key={m.id} className="p-3 bg-gray-50 rounded-lg border border-border-subtle flex justify-between items-center">
                      <div>
                        <span className="text-sm font-bold text-text-navy">{m.name} {m.dosage}</span>
                        <p className="text-xs text-text-muted mt-0.5">{m.frequency} • Started: {m.startDate}</p>
                      </div>
                      <span className="text-[10px] font-bold bg-green-100 text-success px-2 py-0.5 rounded uppercase">
                        Active
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* 5. Allergies Card */}
            <div className="bg-amber-50/60 border-2 border-amber-200 rounded-xl p-5">
              <div className="flex items-center space-x-2 mb-2">
                <AlertTriangle className="w-5 h-5 text-warning" />
                <h3 className="text-base font-bold text-text-navy">Allergies & Sensitivities</h3>
              </div>
              <p className="text-xs text-text-navy font-medium">
                {patient.allergies.length > 0
                  ? patient.allergies.map(a => a.description).join(', ')
                  : 'No known drug allergies (NKDA) documented in patient electronic health record.'}
              </p>
            </div>

            {/* 7. Recent Laboratory Results Card */}
            <div className="bg-white border border-border-subtle rounded-xl p-5 shadow-sm">
              <div className="flex justify-between items-center mb-4">
                <div>
                  <h3 className="text-base font-bold text-text-navy flex items-center">
                    <Activity className="w-4 h-4 mr-2 text-primary" /> Recent Laboratory Results
                  </h3>
                  <p className="text-xs text-text-muted">Most recent CMP panel & renal clearance markers</p>
                </div>
                <button onClick={() => setActiveTab('labs')} className="px-3 py-1.5 bg-primary/10 text-primary rounded-lg text-xs font-bold hover:bg-primary/20 flex items-center">
                  View Full Lab Analysis <ArrowRight className="w-3.5 h-3.5 ml-1" />
                </button>
              </div>

              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-border-subtle">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-2.5 text-left text-xs font-bold text-text-muted uppercase">Test</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold text-text-muted uppercase">Result</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold text-text-muted uppercase">Reference Range</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold text-text-muted uppercase">Date</th>
                      <th className="px-4 py-2.5 text-left text-xs font-bold text-text-muted uppercase">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-subtle">
                    <tr>
                      <td className="px-4 py-3 text-sm font-bold text-text-navy">Serum Creatinine</td>
                      <td className="px-4 py-3 text-sm font-bold text-urgent">1.4 mg/dL ↑</td>
                      <td className="px-4 py-3 text-xs text-text-muted">0.6 - 1.2 mg/dL</td>
                      <td className="px-4 py-3 text-xs text-text-navy font-medium">Aug 10, 2023</td>
                      <td className="px-4 py-3"><span className="text-[10px] font-bold bg-red-100 text-urgent px-2 py-0.5 rounded">ABNORMAL</span></td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 text-sm font-bold text-text-navy">eGFR</td>
                      <td className="px-4 py-3 text-sm font-bold text-urgent">47 mL/min/1.73m² ↓</td>
                      <td className="px-4 py-3 text-xs text-text-muted">60 - 120 mL/min</td>
                      <td className="px-4 py-3 text-xs text-text-navy font-medium">Aug 10, 2023</td>
                      <td className="px-4 py-3"><span className="text-[10px] font-bold bg-red-100 text-urgent px-2 py-0.5 rounded">ABNORMAL</span></td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 text-sm font-bold text-text-navy">Fasting Blood Glucose</td>
                      <td className="px-4 py-3 text-sm font-bold text-text-navy">110 mg/dL</td>
                      <td className="px-4 py-3 text-xs text-text-muted">70 - 99 mg/dL</td>
                      <td className="px-4 py-3 text-xs text-text-navy font-medium">Aug 10, 2023</td>
                      <td className="px-4 py-3"><span className="text-[10px] font-bold bg-yellow-100 text-warning px-2 py-0.5 rounded">ELEVATED</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* 10. Patient Conversation History Card */}
            <div className="bg-white border border-border-subtle rounded-xl p-5 shadow-sm">
              <div className="flex justify-between items-center mb-4">
                <div>
                  <h3 className="text-base font-bold text-text-navy flex items-center">
                    <MessageSquare className="w-4 h-4 mr-2 text-primary" /> Conversation History
                  </h3>
                  <p className="text-xs text-text-muted">Past queries submitted by patient</p>
                </div>
                <button onClick={() => setActiveTab('consultations')} className="text-xs text-primary font-bold hover:underline">
                  View All ({consultations.length})
                </button>
              </div>

              <div className="space-y-3">
                {consultations.map(c => (
                  <div key={c.id} className="p-4 bg-gray-50 rounded-xl border border-border-subtle flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                    <div>
                      <div className="flex items-center space-x-2 mb-1">
                        <span className="text-xs font-bold text-text-navy">
                          {new Date(c.createdAt).toLocaleDateString()}
                        </span>
                        <span className="text-[10px] bg-gray-200 text-text-navy px-1.5 py-0.5 rounded font-mono">
                          {c.intent?.replace('_', ' ')}
                        </span>
                      </div>
                      <p className="text-sm text-text-navy font-medium italic">"{c.query}"</p>
                    </div>

                    <div className="flex items-center space-x-2 shrink-0">
                      <span className={cn(
                        "text-xs px-2.5 py-1 rounded-full font-bold uppercase",
                        c.status === 'doctor_review' ? "bg-yellow-100 text-warning" : "bg-green-100 text-success"
                      )}>
                        {c.status === 'doctor_review' ? 'AI DRAFT READY' : 'APPROVED'}
                      </span>
                      <button 
                        onClick={() => navigate(`/reviews/${c.id}`)}
                        className="px-3 py-1.5 bg-primary text-white text-xs font-bold rounded-lg hover:bg-blue-700 transition-colors"
                      >
                        {c.status === 'doctor_review' ? 'Review →' : 'View'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'timeline' && (
          <div>
            <h3 className="text-lg font-bold text-text-navy mb-4">Patient Longitudinal History</h3>
            <div className="space-y-4">
              {timelineEvents.map(event => (
                <div key={event.id} className="p-4 border border-border-subtle rounded-xl flex items-start space-x-3 bg-gray-50">
                  <Clock className="w-5 h-5 text-primary shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <div className="flex justify-between items-start mb-1">
                      <h4 className="font-bold text-text-navy">{event.title}</h4>
                      <span className="text-xs text-text-muted px-2 py-1 bg-white rounded border border-border-subtle font-mono">
                        {event.date}
                      </span>
                    </div>
                    <p className="text-sm text-text-muted">{event.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        
        {activeTab === 'labs' && (
          <div className="space-y-8">
            <div>
              <h3 className="text-lg font-bold text-text-navy mb-2">Longitudinal Lab Trend Analysis</h3>
              <p className="text-xs text-text-muted mb-4">Creatinine & eGFR trajectory over 4 consecutive lab readings</p>
              
              <div className="h-64 mb-6">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={labDataPoints}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis domain={[0, 2]} />
                    <RechartsTooltip />
                    <Line type="monotone" dataKey="value" stroke="#EF4444" strokeWidth={3} name="Creatinine (mg/dL)" activeDot={{ r: 8 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              <table className="min-w-full divide-y divide-border-subtle mb-6">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2.5 text-left text-xs font-bold text-text-muted">Test</th>
                    <th className="px-4 py-2.5 text-left text-xs font-bold text-text-muted">Value</th>
                    <th className="px-4 py-2.5 text-left text-xs font-bold text-text-muted">Reference Range</th>
                    <th className="px-4 py-2.5 text-left text-xs font-bold text-text-muted">Date</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  <tr><td className="px-4 py-3 font-bold text-text-navy">Creatinine</td><td className="px-4 py-3 text-urgent font-bold">1.4 mg/dL ↑</td><td className="px-4 py-3 text-xs text-text-muted">0.6 - 1.2 mg/dL</td><td className="px-4 py-3 text-xs font-medium">Aug 10, 2023</td></tr>
                  <tr><td className="px-4 py-3 font-bold text-text-navy">eGFR</td><td className="px-4 py-3 text-urgent font-bold">47 mL/min ↓</td><td className="px-4 py-3 text-xs text-text-muted">60 - 120 mL/min</td><td className="px-4 py-3 text-xs font-medium">Aug 10, 2023</td></tr>
                </tbody>
              </table>
            </div>

            {/* MODULE 3: Side-by-Side Time Point Comparison Component */}
            <div className="bg-blue-50/60 p-5 rounded-xl border-2 border-primary/20 space-y-4">
              <div className="flex justify-between items-center border-b border-blue-200 pb-3">
                <h4 className="font-bold text-text-navy text-sm flex items-center">
                  <Activity className="w-4 h-4 mr-2 text-primary" />
                  Side-by-Side Lab Time Point Comparison
                </h4>
                <span className="text-xs bg-primary text-white font-bold px-2 py-0.5 rounded uppercase">Module 3 Tool</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-text-navy mb-1">Time Point A (Baseline)</label>
                  <select 
                    value={pointAIdx} 
                    onChange={e => setPointAIdx(Number(e.target.value))}
                    className="w-full border border-border-subtle rounded p-2 text-xs text-black"
                  >
                    {labDataPoints.map((pt, idx) => (
                      <option key={pt.date} value={idx}>{pt.date} — Creatinine: {pt.value} mg/dL</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-bold text-text-navy mb-1">Time Point B (Comparison)</label>
                  <select 
                    value={pointBIdx} 
                    onChange={e => setPointBIdx(Number(e.target.value))}
                    className="w-full border border-border-subtle rounded p-2 text-xs text-black"
                  >
                    {labDataPoints.map((pt, idx) => (
                      <option key={pt.date} value={idx}>{pt.date} — Creatinine: {pt.value} mg/dL</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="bg-white p-4 rounded-lg border border-border-subtle grid grid-cols-1 md:grid-cols-3 gap-4 text-center items-center">
                <div className="p-3 bg-gray-50 rounded">
                  <p className="text-xs text-text-muted font-medium">Time Point A ({pointA.date})</p>
                  <p className="text-lg font-bold text-text-navy">{pointA.value} mg/dL</p>
                  <p className="text-[11px] text-text-muted">eGFR: {pointA.egfr} mL/min</p>
                </div>
                <div className="p-3 bg-blue-50 rounded flex flex-col items-center justify-center">
                  <p className="text-xs text-primary font-bold uppercase">Delta Trajectory</p>
                  <p className={`text-xl font-bold ${Number(absDelta) > 0 ? 'text-urgent' : 'text-success'}`}>
                    {Number(absDelta) > 0 ? `+${absDelta}` : absDelta} mg/dL
                  </p>
                  <p className="text-xs font-semibold text-text-navy">({Number(pctDelta) > 0 ? `+${pctDelta}` : pctDelta}%)</p>
                </div>
                <div className="p-3 bg-gray-50 rounded">
                  <p className="text-xs text-text-muted font-medium">Time Point B ({pointB.date})</p>
                  <p className="text-lg font-bold text-urgent">{pointB.value} mg/dL</p>
                  <p className="text-[11px] text-text-muted">eGFR: {pointB.egfr} mL/min</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'medications' && (
          <div>
            <h3 className="text-lg font-bold text-text-navy mb-4">Medications</h3>
            <table className="min-w-full divide-y divide-border-subtle">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-bold text-text-muted uppercase">Medication</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-text-muted uppercase">Dosage</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-text-muted uppercase">Frequency</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-text-muted uppercase">Start Date</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-text-muted uppercase">Status</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-border-subtle">
                {patient.medications.map(m => (
                  <tr key={m.id}>
                    <td className="px-4 py-4 font-bold text-text-navy">{m.name}</td>
                    <td className="px-4 py-4 text-sm">{m.dosage}</td>
                    <td className="px-4 py-4 text-sm">{m.frequency}</td>
                    <td className="px-4 py-4 text-sm text-text-muted">{m.startDate}</td>
                    <td className="px-4 py-4">
                      {m.active ? (
                        <span className="px-2.5 py-1 text-xs font-bold bg-green-100 text-success rounded-full">Active</span>
                      ) : (
                        <span className="px-2.5 py-1 text-xs font-semibold bg-gray-100 text-text-muted rounded-full">Stopped {m.stopDate}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'documents' && (
          <div>
            <h3 className="text-lg font-bold text-text-navy mb-4">Documents</h3>
            {documents.length === 0 ? (
              <div className="text-center text-text-muted py-12">
                No documents uploaded yet.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {documents.map(d => (
                  <div key={d.id} className="p-4 border border-border-subtle rounded-xl flex items-start space-x-3 hover:border-primary cursor-pointer transition-colors bg-gray-50/50">
                    <FileText className="w-8 h-8 text-primary shrink-0" />
                    <div>
                      <h4 className="text-sm font-bold text-text-navy line-clamp-1">{d.name}</h4>
                      <div className="mt-1 flex flex-wrap gap-2 text-xs text-text-muted">
                        <span className="bg-gray-100 px-1.5 py-0.5 rounded">{d.category.replace('_', ' ')}</span>
                        <span>{d.uploadedAt}</span>
                        <span>{d.size}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'consultations' && (
          <div>
            <h3 className="text-lg font-bold text-text-navy mb-4">Consultations History</h3>
            <table className="min-w-full divide-y divide-border-subtle">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-bold text-text-muted uppercase">Date</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-text-muted uppercase">Query</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-text-muted uppercase">Intent</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-text-muted uppercase">Urgency</th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-text-muted uppercase">Status</th>
                  <th className="px-4 py-3 text-right text-xs font-bold text-text-muted uppercase">Action</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-border-subtle">
                {consultations.map(c => (
                  <tr key={c.id} onClick={() => navigate(`/reviews/${c.id}`)} className="hover:bg-gray-50 cursor-pointer">
                    <td className="px-4 py-4 text-sm text-text-muted">{new Date(c.createdAt).toLocaleDateString()}</td>
                    <td className="px-4 py-4 text-sm font-medium text-text-navy truncate max-w-[200px]">{c.query}</td>
                    <td className="px-4 py-4 text-sm">
                      <span className="bg-gray-100 px-2 py-1 rounded text-xs font-mono">{c.intent?.replace('_', ' ')}</span>
                    </td>
                    <td className="px-4 py-4">
                      <span className={cn(
                        "text-xs px-2.5 py-1 rounded-full font-bold uppercase",
                        c.urgency === 'urgent' ? 'bg-red-100 text-urgent' :
                        c.urgency === 'soon' ? 'bg-yellow-100 text-warning' : 'bg-blue-100 text-primary'
                      )}>
                        {c.urgency?.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-4">
                      <span className="text-xs px-2 py-1 bg-gray-100 rounded-full font-bold">{c.status.replace('_', ' ')}</span>
                    </td>
                    <td className="px-4 py-4 text-right text-sm font-bold text-primary hover:text-blue-700">View →</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'appointments' && (
          <div>
            <h3 className="text-lg font-bold text-text-navy mb-4">Appointments</h3>
            {appointments.length === 0 ? (
              <div className="text-center text-text-muted py-12">
                No upcoming appointments.
              </div>
            ) : (
              <div className="space-y-4">
                {appointments.map(a => (
                  <div key={a.id} className="p-4 border border-border-subtle rounded-xl flex justify-between items-center bg-gray-50">
                    <div>
                      <div className="flex items-center space-x-2">
                        <Calendar className="w-4 h-4 text-text-muted" />
                        <span className="font-bold text-text-navy">{a.date} at {a.time}</span>
                      </div>
                      <p className="text-sm text-text-muted mt-1">{a.reason} • {a.doctorName}</p>
                    </div>
                    <div>
                      <span className={cn(
                        "px-2.5 py-1 text-xs font-bold rounded-full uppercase",
                        a.status === 'confirmed' ? "bg-green-100 text-success" :
                        a.status === 'completed' ? "bg-gray-200 text-text-muted" :
                        "bg-yellow-100 text-warning"
                      )}>
                        {a.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
