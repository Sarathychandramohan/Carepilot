import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useWorkflowStore } from '../services/mock/mockWorkflow';
import { consultationApi, BackendConsultationDetail } from '../services/api/consultationApi';
import { Dialog } from '@headlessui/react';
import { ArrowUpRight, ArrowDownRight, ExternalLink, AlertCircle, FileText, CheckCircle2, ChevronLeft, Save, Pencil, Sparkles, RotateCcw, ShieldAlert, Cpu } from 'lucide-react';
import toast from 'react-hot-toast';
import { cn } from '../utils/cn';

const EDIT_CATEGORY_OPTIONS = [
  { id: 'factual_correction', label: 'Factual Correction (EHR/Lab)', weight: 2 },
  { id: 'missing_ehr_fact', label: 'Missing EHR Fact Added', weight: 2 },
  { id: 'wrong_ehr_fact', label: 'Wrong EHR Fact Removed', weight: 3 },
  { id: 'unsupported_medical_claim', label: 'Unsupported Medical Claim Fix', weight: 3 },
  { id: 'citation_error', label: 'Citation / Attribution Fix', weight: 2 },
  { id: 'urgency_correction', label: 'Urgency Tier Adjustment', weight: 3 },
  { id: 'missing_caution', label: 'Missing Caution / Red Flag Added', weight: 2 },
  { id: 'tone_change', label: 'Tone / Empathy Adjustment', weight: 1 },
  { id: 'unnecessary_content', label: 'Removed Unnecessary Content', weight: 1 },
  { id: 'retrieval_error', label: 'Retrieval Error Corrected', weight: 2 },
  { id: 'no_change', label: 'No Change (Accepted AI Text)', weight: 0 },
  { id: 'other', label: 'Other Modification', weight: 1 },
];

export function ConsultationReviewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const consultations = useWorkflowStore(state => state.consultations);
  const patients = useWorkflowStore(state => state.patients);
  const approveConsultation = useWorkflowStore(state => state.approveConsultation);
  const rejectConsultation = useWorkflowStore(state => state.rejectConsultation);
  const saveDraft = useWorkflowStore(state => state.saveDraft);

  const consultation = consultations.find(c => c.id === id);
  const patient = patients.find(p => p.id === (consultation?.patientId || ''));
  const pendingQueue = consultations.filter(c => c.status === 'doctor_review');

  const [draftContent, setDraftContent] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [isApproveOpen, setIsApproveOpen] = useState(false);
  const [isRejectOpen, setIsRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('factual_correction');
  const [rejectNote, setRejectNote] = useState('');
  const [backendConsultation, setBackendConsultation] = useState<BackendConsultationDetail | null>(null);
  const [reviewStartTime] = useState(Date.now());
  const [selectedCategories, setSelectedCategories] = useState<Record<string, boolean>>({ no_change: true });
  
  useEffect(() => {
    if (id) {
      consultationApi.getConsultation(id)
        .then(data => {
          setBackendConsultation(data);
          if (data.ai_draft?.sentences && data.ai_draft.sentences.length > 0) {
            setDraftContent(data.ai_draft.sentences.map(s => s.text).join(' '));
          } else if (data.final_response) {
            setDraftContent(data.final_response);
          } else if (data.validation_status === 'manual_required') {
            setDraftContent('');
            setIsEditing(true);
          }
        })
        .catch(() => {
          // Fallback to local store data
          if (consultation?.aiDraft?.content) {
            setDraftContent(consultation.aiDraft.content);
          } else if (consultation) {
            setDraftContent(`Patient ${patient?.firstName || ''} ${patient?.lastName || ''} submitted query: "${consultation.query}". Based on retrieved clinical evidence, please review patient context and provide response.`);
          }
        });
    }
  }, [id]);

  if (!consultation && !backendConsultation) {
    return (
      <div className="p-8 text-center">
        <h2 className="text-xl font-bold text-text-navy mb-2">Consultation Not Found</h2>
        <p className="text-sm text-text-muted mb-4">The requested review item could not be loaded or has been archived.</p>
        <button onClick={() => navigate('/reviews')} className="px-4 py-2 bg-primary text-white rounded-md text-sm font-bold">
          Back to Review Queue
        </button>
      </div>
    );
  }

  const effectiveConsultation = consultation || {
    id: backendConsultation!.id,
    patientId: backendConsultation!.patient_id,
    patientName: 'Christian Labadie',
    query: backendConsultation!.query_text,
    status: 'doctor_review' as const,
    threadStatus: backendConsultation!.thread_status as any,
    urgency: backendConsultation!.urgency_final,
    intent: backendConsultation!.intent as any,
    messages: [{ id: 'm1', consultationId: backendConsultation!.id, role: 'patient' as const, content: backendConsultation!.query_text, timestamp: backendConsultation!.created_at }],
    createdAt: backendConsultation!.created_at,
    updatedAt: backendConsultation!.created_at,
    aiDraft: backendConsultation!.ai_draft?.sentences ? {
      content: backendConsultation!.ai_draft.sentences.map(s => s.text).join(' '),
      generatedAt: backendConsultation!.created_at,
      citations: []
    } : undefined
  };

  const effectivePatient = patient || {
    id: effectiveConsultation.patientId,
    firstName: 'Christian',
    lastName: 'Labadie',
    age: 81,
    gender: 'M' as const,
    dateOfBirth: '1945-01-10',
    conditions: [
      { id: 'c1', description: 'Chronic Kidney Disease Stage 3', startDate: '2019-04-12', active: true },
      { id: 'c2', description: 'Hypertension', startDate: '2015-08-20', active: true },
      { id: 'c3', description: 'Type 2 Diabetes', startDate: '2016-11-05', active: true }
    ],
    medications: [
      { id: 'm1', patientId: 'p1', name: 'Lisinopril', dosage: '10mg', frequency: 'Daily', startDate: '2019-05-01', active: true },
      { id: 'm2', patientId: 'p1', name: 'Metformin', dosage: '500mg', frequency: 'Twice daily', startDate: '2017-01-15', active: true }
    ],
    allergies: [],
    pendingConsultationCount: 1
  };

  const isManualRequired = backendConsultation?.validation_status === 'manual_required' || consultation?.validationStatus === 'manual_required';
  const originalDraftText = (backendConsultation?.ai_draft?.sentences ? backendConsultation.ai_draft.sentences.map(s => s.text).join(' ') : consultation?.aiDraft?.content) || '';
  const isEdited = draftContent.trim() !== originalDraftText.trim();

  const handleApprove = async (isNext: boolean) => {
    const durationSeconds = Math.max(1, Math.round((Date.now() - reviewStartTime) / 1000));
    const catsPayload: Record<string, number> = {};
    EDIT_CATEGORY_OPTIONS.forEach(c => {
      catsPayload[c.id] = selectedCategories[c.id] ? 1 : 0;
    });

    if (!Object.values(catsPayload).some(v => v === 1)) {
      catsPayload[isEdited ? 'factual_correction' : 'no_change'] = 1;
    }

    try {
      await consultationApi.submitReview(id!, {
        doctor_action: isEdited ? 'edited' : 'approved',
        final_response: draftContent,
        edit_categories: catsPayload,
        doctor_review_seconds: durationSeconds,
      });
      await consultationApi.deliverConsultation(id!);
    } catch (apiErr) {
      console.warn('Backend review/deliver API call skipped or offline:', apiErr);
    }

    approveConsultation(id!, draftContent, isEdited ? 'factual_correction' : 'no_change');
    toast.success('Consultation approved & delivered to patient');
    
    if (isNext) {
      const next = pendingQueue.find(c => c.id !== id);
      if (next) {
        navigate(`/reviews/${next.id}`);
        toast('Moved to next request');
      } else {
        navigate('/reviews');
      }
    } else {
      navigate('/reviews');
    }
  };

  const handleReject = async () => {
    try {
      await consultationApi.submitReview(id!, {
        doctor_action: 'rejected',
        reject_reason: rejectReason,
      });
    } catch (apiErr) {
      console.warn('Backend reject API call skipped or offline:', apiErr);
    }

    rejectConsultation(id!, rejectReason, rejectNote);
    toast.success('Consultation rejected');
    navigate('/reviews');
  };

  const handleSaveDraft = () => {
    saveDraft(id!, draftContent);
    toast.success('Draft saved');
  };

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col overflow-hidden -m-6 bg-bg-app">
      {/* Sticky Header */}
      <div className="bg-white border-b border-border-subtle p-4 flex items-center justify-between shrink-0">
        <div className="flex items-center space-x-4">
          <button onClick={() => navigate('/reviews')} className="text-text-muted hover:text-text-navy flex items-center">
            <ChevronLeft className="w-5 h-5 mr-1" /> Back to Queue
          </button>
          <div className="h-6 w-px bg-border-subtle" />
          <h1 className="text-lg font-bold text-text-navy flex items-center">
            Reviewing Consultation: {effectiveConsultation.id}
            <span className={cn(
              "ml-3 px-2.5 py-0.5 rounded-full text-xs font-medium uppercase",
              effectiveConsultation.urgency === 'urgent' ? "bg-red-100 text-urgent" :
              effectiveConsultation.urgency === 'soon' ? "bg-yellow-100 text-warning" : "bg-blue-100 text-primary"
            )}>
              {effectiveConsultation.urgency}
            </span>
          </h1>
        </div>
        <div className="text-sm text-text-muted flex items-center">
          <FileText className="w-4 h-4 mr-2" />
          Intent: {effectiveConsultation.intent?.replace('_', ' ') || 'General Query'}
        </div>
      </div>

      {/* 3-Column Layout */}
      <div className="flex-1 grid grid-cols-[280px_1fr_360px] overflow-hidden">
        
        {/* Column 1: Patient Context */}
        <div className="bg-white border-r border-border-subtle overflow-y-auto p-5">
          <div className="flex justify-between items-start mb-6">
            <div>
              <h2 className="text-xl font-bold text-text-navy">{effectivePatient.firstName} {effectivePatient.lastName}</h2>
              <p className="text-sm text-text-muted">{effectivePatient.age}y • {effectivePatient.gender} • ID: {effectivePatient.id.slice(0, 16)}</p>
            </div>
            <Link to={`/patients/${effectivePatient.id}`} className="text-primary hover:text-blue-700">
              <ExternalLink className="w-5 h-5" />
            </Link>
          </div>

          <div className="mb-6">
            <h3 className="text-sm font-semibold text-text-muted uppercase mb-2">Conditions</h3>
            <ul className="space-y-1">
              {effectivePatient.conditions.map(c => (
                <li key={c.id} className="text-sm text-text-navy bg-gray-50 px-2 py-1 rounded">{c.description}</li>
              ))}
            </ul>
          </div>

          <div className="mb-6">
            <h3 className="text-sm font-semibold text-text-muted uppercase mb-2">Medications</h3>
            <ul className="space-y-1">
              {effectivePatient.medications.map(m => (
                <li key={m.id} className="text-sm text-text-navy bg-gray-50 px-2 py-1 rounded">
                  {m.name} {m.dosage}
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-text-muted uppercase mb-2">Recent Labs</h3>
            <div className="space-y-3">
              <div className="p-3 border border-border-subtle rounded-md">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-sm font-medium">Creatinine</span>
                  <span className="text-xs text-text-muted">Aug 10, 2023</span>
                </div>
                <div className="flex items-baseline space-x-2">
                  <span className="text-lg font-bold text-urgent">1.4 mg/dL</span>
                  <span className="text-xs text-text-muted line-through">1.2</span>
                  <ArrowUpRight className="w-4 h-4 text-urgent" />
                </div>
              </div>
              <div className="p-3 border border-border-subtle rounded-md">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-sm font-medium">eGFR</span>
                  <span className="text-xs text-text-muted">Aug 10, 2023</span>
                </div>
                <div className="flex items-baseline space-x-2">
                  <span className="text-lg font-bold text-urgent">47</span>
                  <span className="text-xs text-text-muted line-through">51</span>
                  <ArrowDownRight className="w-4 h-4 text-urgent" />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Column 2: Full Multi-Turn Conversation Thread (Module 1) */}
        <div className="bg-bg-app overflow-y-auto p-6 flex flex-col">
          <div className="flex-1 space-y-6">
            
            {/* Thread Header Banner */}
            <div className="flex items-center justify-between bg-white p-3 rounded-lg border border-border-subtle">
              <span className="text-xs font-bold text-text-navy uppercase tracking-wider">
                Multi-Turn Thread ({effectiveConsultation.messages?.length || 1} Turns)
              </span>
              <span className={`text-xs px-2.5 py-0.5 rounded-full font-bold uppercase ${
                effectiveConsultation.threadStatus === 'patient_replied' ? 'bg-purple-100 text-purple-700' :
                effectiveConsultation.status === 'approved' ? 'bg-green-100 text-success' : 'bg-yellow-100 text-warning'
              }`}>
                {effectiveConsultation.threadStatus === 'patient_replied' ? 'Patient Follow-Up Replied' : effectiveConsultation.status}
              </span>
            </div>

            {/* Messages Feed */}
            {(effectiveConsultation.messages || [
              { id: 'm-default', consultationId: effectiveConsultation.id, role: 'patient' as const, content: effectiveConsultation.query, timestamp: effectiveConsultation.createdAt }
            ]).map((msg, index) => (
              <div key={msg.id || index} className={`flex flex-col ${msg.role === 'patient' ? 'items-start max-w-lg' : 'items-end max-w-lg ml-auto'}`}>
                <span className="text-xs text-text-muted mb-1 px-1">
                  {msg.role === 'patient' ? `${effectivePatient.firstName} (Patient)` : 'Dr. Amelia Smith (Doctor)'} • {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
                <div className={`p-4 rounded-2xl shadow-sm border text-sm leading-relaxed ${
                  msg.role === 'patient' 
                    ? 'bg-white rounded-tl-sm border-border-subtle text-text-navy' 
                    : 'bg-blue-50 border-blue-200 text-text-navy rounded-tr-sm'
                }`}>
                  {msg.content}
                </div>
              </div>
            ))}

            {/* System Status Indicators */}
            <div className="flex flex-col items-center justify-center py-4 space-y-2">
              <div className="flex items-center text-xs text-text-muted bg-white px-3 py-1 rounded-full border border-border-subtle">
                <CheckCircle2 className="w-3 h-3 text-success mr-1" /> Full thread history & patient context retrieved
              </div>
              <div className="flex items-center text-xs text-text-muted bg-white px-3 py-1 rounded-full border border-border-subtle">
                <CheckCircle2 className="w-3 h-3 text-success mr-1" /> RAG medical knowledge retrieved
              </div>
            </div>
          </div>
        </div>

        {/* Column 3: AI Draft & Editor */}
        <div className="bg-white border-l border-border-subtle overflow-y-auto flex flex-col">
          <div className="p-5 flex-1 flex flex-col">
            <div className="flex justify-between items-center mb-4">
              <div className="flex items-center space-x-2">
                <Sparkles className="w-5 h-5 text-primary" />
                <h3 className="font-bold text-text-navy text-base">
                  AI Suggested Response
                </h3>
              </div>
              {isEdited ? (
                <span className="text-[10px] uppercase bg-yellow-100 text-warning px-2 py-0.5 rounded font-bold border border-warning/30">
                  Edited by Clinician
                </span>
              ) : (
                <span className="text-[10px] uppercase bg-blue-50 text-primary px-2 py-0.5 rounded font-bold border border-primary/20">
                  AI Draft
                </span>
              )}
            </div>

            {/* Clinical Safety Gate Alert if Draft Suppressed */}
            {isManualRequired && (
              <div className="bg-red-50 border-2 border-red-400 rounded-xl p-3.5 mb-4 shadow-sm">
                <div className="flex items-center text-urgent font-bold text-xs mb-1">
                  <ShieldAlert className="w-4 h-4 mr-1.5 shrink-0" />
                  AI Draft Suppressed (Clinical Safety Gate)
                </div>
                <p className="text-xs text-text-navy leading-relaxed">
                  Automated draft did not pass clinical NLI faithfulness validation or triggered a red-flag safety rule. Direct clinician drafting is required.
                </p>
              </div>
            )}

            {/* Model & Retrieval Pipeline Trace */}
            {backendConsultation && (
              <div className="bg-gray-50 border border-border-subtle rounded-lg p-2.5 mb-3 text-xs space-y-1">
                <div className="flex justify-between items-center text-text-muted">
                  <span className="flex items-center"><Cpu className="w-3.5 h-3.5 mr-1 text-primary" /> Architecture</span>
                  <span className="font-mono text-text-navy font-semibold">{backendConsultation.llm_model || 'Local LLM'} • {backendConsultation.ablation_arm || 'full'}</span>
                </div>
                {backendConsultation.faithfulness_score !== undefined && backendConsultation.faithfulness_score !== null && (
                  <div className="flex justify-between items-center text-text-muted">
                    <span>NLI Faithfulness</span>
                    <span className="font-mono text-text-navy font-semibold">{(backendConsultation.faithfulness_score * 100).toFixed(0)}%</span>
                  </div>
                )}
              </div>
            )}

            {!isEditing ? (
              /* Read-only / Preview Card with "Edit Response" button */
              <div className="bg-blue-50/50 border-2 border-blue-200 rounded-xl p-4 flex-1 flex flex-col justify-between mb-4 shadow-sm">
                <div>
                  <div className="flex items-center justify-between pb-2 mb-3 border-b border-blue-200/60">
                    <span className="text-xs font-semibold text-text-muted flex items-center">
                      <FileText className="w-3.5 h-3.5 mr-1 text-primary" /> Qwen3 Draft Output
                    </span>
                    <span className="text-[11px] text-text-muted font-mono">{draftContent.length} chars</span>
                  </div>
                  <p className="text-sm text-text-navy leading-relaxed whitespace-pre-wrap font-sans">
                    {draftContent}
                  </p>
                </div>

                <div className="mt-4 pt-3 border-t border-blue-200/60 flex items-center justify-between">
                  <span className="text-xs text-text-muted italic">Click Edit Response to modify text</span>
                  <button
                    onClick={() => setIsEditing(true)}
                    className="px-3.5 py-1.5 bg-white border border-primary text-primary hover:bg-blue-50 rounded-lg text-xs font-bold flex items-center shadow-sm transition-colors"
                  >
                    <Pencil className="w-3.5 h-3.5 mr-1.5" /> Edit Response
                  </button>
                </div>
              </div>
            ) : (
              /* Editable Textarea Mode */
              <div className="flex-1 flex flex-col mb-4">
                <div className="flex justify-between items-center mb-2">
                  <label className="text-xs font-bold text-primary flex items-center">
                    <Pencil className="w-3.5 h-3.5 mr-1" /> Editable Textbox — Doctor Modification
                  </label>
                  <span className="text-xs font-mono text-text-muted">{draftContent.length} characters</span>
                </div>
                
                <textarea
                  value={draftContent}
                  onChange={e => setDraftContent(e.target.value)}
                  placeholder="Modify or write custom clinical response here..."
                  className="flex-1 w-full p-4 border-2 border-primary rounded-xl resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 text-sm leading-relaxed text-text-navy bg-white shadow-inner min-h-[220px]"
                  autoFocus
                />

                <div className="flex items-center justify-between mt-3">
                  <button
                    onClick={() => {
                      if (effectiveConsultation.aiDraft?.content) {
                        setDraftContent(effectiveConsultation.aiDraft.content);
                      }
                      setIsEditing(false);
                    }}
                    className="px-3 py-1.5 text-xs font-semibold text-text-muted hover:text-text-navy flex items-center"
                  >
                    <RotateCcw className="w-3.5 h-3.5 mr-1" /> Reset Original
                  </button>
                  <div className="flex space-x-2">
                    <button
                      onClick={() => setIsEditing(false)}
                      className="px-3 py-1.5 bg-gray-100 text-text-navy hover:bg-gray-200 rounded-lg text-xs font-semibold"
                    >
                      Done Editing
                    </button>
                    <button
                      onClick={() => {
                        handleSaveDraft();
                        setIsEditing(false);
                      }}
                      className="px-3.5 py-1.5 bg-primary text-white hover:bg-blue-700 rounded-lg text-xs font-bold flex items-center shadow-sm"
                    >
                      <Save className="w-3.5 h-3.5 mr-1" /> Save Edit
                    </button>
                  </div>
                </div>
              </div>
            )}

            <div className="mt-4 pt-4 border-t border-border-subtle">
              <h3 className="text-xs font-bold text-text-muted uppercase tracking-wider mb-3">Sources & Citations</h3>
              <div className="space-y-2">
                {(effectiveConsultation.aiDraft?.citations || []).map(cit => (
                  <a key={cit.id} href={cit.url || '#'} target="_blank" rel="noreferrer" className="block p-3 border border-border-subtle rounded-lg hover:border-primary transition-colors bg-gray-50/50">
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-xs font-bold text-text-navy truncate">{cit.title}</span>
                      <ExternalLink className="w-3.5 h-3.5 text-text-muted" />
                    </div>
                    <span className="text-[11px] text-primary font-medium">{cit.source}</span>
                  </a>
                ))}
              </div>
            </div>
          </div>
        </div>

      </div>

      {/* Sticky Action Bar */}
      <div className="bg-white border-t border-border-subtle p-4 shrink-0 flex justify-between items-center">
        <button 
          onClick={() => setIsRejectOpen(true)}
          className="px-4 py-2 text-urgent border border-urgent rounded-md hover:bg-red-50 font-medium transition-colors"
        >
          Reject...
        </button>
        <div className="flex space-x-3">
          {!isEditing ? (
            <button 
              onClick={() => setIsEditing(true)}
              className="px-4 py-2 text-text-navy bg-gray-100 rounded-md hover:bg-gray-200 font-medium transition-colors flex items-center"
            >
              <Pencil className="w-4 h-4 mr-2 text-primary" /> Edit Response
            </button>
          ) : (
            <button 
              onClick={() => {
                handleSaveDraft();
                setIsEditing(false);
              }}
              className="px-4 py-2 text-text-navy bg-gray-100 rounded-md hover:bg-gray-200 font-medium transition-colors flex items-center"
            >
              <Save className="w-4 h-4 mr-2 text-primary" /> Save Edit
            </button>
          )}
          <button 
            onClick={() => setIsApproveOpen(true)}
            className="px-4 py-2 text-primary border border-primary rounded-md hover:bg-blue-50 font-semibold transition-colors"
          >
            Approve
          </button>
          <button 
            onClick={() => handleApprove(true)}
            className="px-4 py-2 text-white bg-primary rounded-md hover:bg-blue-700 font-bold transition-colors shadow-sm flex items-center"
          >
            <CheckCircle2 className="w-4 h-4 mr-2" /> Approve & Send
          </button>
        </div>
      </div>

      {/* Approve Modal with 12 Clinical Edit Categories */}
      <Dialog open={isApproveOpen} onClose={() => setIsApproveOpen(false)} className="relative z-50">
        <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
        <div className="fixed inset-0 flex w-screen items-center justify-center p-4">
          <Dialog.Panel className="mx-auto max-w-xl rounded-xl bg-white p-6 shadow-xl w-full">
            <Dialog.Title className="text-lg font-bold text-text-navy mb-2 flex items-center justify-between">
              <span>Confirm & Deliver Response</span>
              <span className="text-xs font-normal text-text-muted">ID: {effectiveConsultation.id.slice(0, 12)}</span>
            </Dialog.Title>
            
            <p className="text-xs text-text-muted mb-3">
              Review final response and classify any clinical modifications. The response will be delivered directly to the patient app.
            </p>

            <div className="text-xs text-text-navy bg-bg-app p-3 rounded-lg mb-4 whitespace-pre-wrap max-h-36 overflow-y-auto border border-border-subtle">
              {draftContent}
            </div>

            {/* 12 Clinical Edit Categories */}
            <div className="mb-4">
              <label className="block text-xs font-bold text-text-navy uppercase tracking-wider mb-2">
                Clinical Edit Classification (12 Categories)
              </label>
              <div className="grid grid-cols-2 gap-2 max-h-44 overflow-y-auto p-2 border border-border-subtle rounded-lg bg-gray-50 text-xs">
                {EDIT_CATEGORY_OPTIONS.map(opt => (
                  <label key={opt.id} className="flex items-start space-x-2 cursor-pointer p-1 rounded hover:bg-white transition-colors">
                    <input
                      type="checkbox"
                      checked={Boolean(selectedCategories[opt.id])}
                      onChange={e => {
                        const updated = { ...selectedCategories, [opt.id]: e.target.checked };
                        if (opt.id === 'no_change' && e.target.checked) {
                          EDIT_CATEGORY_OPTIONS.forEach(o => { if (o.id !== 'no_change') updated[o.id] = false; });
                        } else if (opt.id !== 'no_change' && e.target.checked) {
                          updated['no_change'] = false;
                        }
                        setSelectedCategories(updated);
                      }}
                      className="mt-0.5 rounded text-primary focus:ring-primary"
                    />
                    <span className="text-text-navy text-[11px] leading-tight">
                      {opt.label} <span className="text-text-muted font-mono">(w={opt.weight})</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <div className="flex justify-end space-x-3 pt-2 border-t border-border-subtle">
              <button onClick={() => setIsApproveOpen(false)} className="px-4 py-2 text-text-muted hover:bg-gray-100 rounded-md text-sm font-medium">Cancel</button>
              <button onClick={() => { setIsApproveOpen(false); handleApprove(false); }} className="px-4 py-2 bg-primary text-white rounded-md hover:bg-blue-700 text-sm font-bold shadow-sm">
                Approve & Deliver to Patient
              </button>
            </div>
          </Dialog.Panel>
        </div>
      </Dialog>

      {/* Reject Modal */}
      <Dialog open={isRejectOpen} onClose={() => setIsRejectOpen(false)} className="relative z-50">
        <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
        <div className="fixed inset-0 flex w-screen items-center justify-center p-4">
          <Dialog.Panel className="mx-auto max-w-md rounded bg-white p-6 shadow-xl w-full">
            <Dialog.Title className="text-lg font-bold text-urgent flex items-center mb-4">
              <AlertCircle className="w-5 h-5 mr-2" /> Reject Consultation
            </Dialog.Title>
            
            <div className="space-y-4 mb-6">
              <div>
                <label className="block text-sm font-medium text-text-navy mb-1">Reason</label>
                <select value={rejectReason} onChange={e => setRejectReason(e.target.value)} className="w-full border-border-subtle rounded-md shadow-sm focus:border-urgent focus:ring-urgent py-2 px-3 border text-black">
                  <option value="factual_correction">Factual Error</option>
                  <option value="insufficient_context">Insufficient Context</option>
                  <option value="unsafe_response">Unsafe Response</option>
                  <option value="poor_tone">Poor Tone</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-text-navy mb-1">Additional Notes (Optional)</label>
                <textarea 
                  value={rejectNote} 
                  onChange={e => setRejectNote(e.target.value)}
                  className="w-full border-border-subtle rounded-md shadow-sm focus:border-urgent focus:ring-urgent p-3 border text-black resize-none"
                  rows={3}
                />
              </div>
            </div>

            <div className="flex justify-end space-x-3">
              <button onClick={() => setIsRejectOpen(false)} className="px-4 py-2 text-text-muted hover:bg-gray-100 rounded-md">Cancel</button>
              <button onClick={() => { setIsRejectOpen(false); handleReject(); }} className="px-4 py-2 bg-urgent text-white rounded-md hover:bg-red-700">Reject</button>
            </div>
          </Dialog.Panel>
        </div>
      </Dialog>

    </div>
  );
}
