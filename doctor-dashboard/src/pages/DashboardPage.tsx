import { useWorkflowStore } from '../services/mock/mockWorkflow';
import { useNavigate } from 'react-router-dom';
import { Activity, Clock, AlertTriangle, CheckCircle2 } from 'lucide-react';

export function DashboardPage() {
  const consultations = useWorkflowStore(state => state.consultations);
  const navigate = useNavigate();

  const pending = consultations.filter(c => c.status === 'doctor_review');
  const urgent = pending.filter(c => c.urgency === 'urgent');
  // Mock today based on total
  const todayCount = consultations.length; 
  const reviewed = consultations.filter(c => c.status === 'approved' || c.status === 'rejected');

  const topPending = [...pending].sort((a, b) => {
    const weights: Record<string, number> = { urgent: 3, soon: 2, routine: 1 };
    return (weights[b.urgency || 'routine'] || 0) - (weights[a.urgency || 'routine'] || 0);
  }).slice(0, 5);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-text-navy">Overview</h1>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-6 rounded-lg shadow-sm border border-border-subtle">
          <div className="flex items-center">
            <div className="p-3 bg-blue-50 text-primary rounded-full">
              <Clock className="w-6 h-6" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-text-muted">Pending Reviews</p>
              <p className="text-2xl font-semibold text-text-navy">{pending.length}</p>
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border border-border-subtle">
          <div className="flex items-center">
            <div className="p-3 bg-red-50 text-urgent rounded-full">
              <AlertTriangle className="w-6 h-6" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-text-muted">Urgent Cases</p>
              <p className="text-2xl font-semibold text-text-navy">{urgent.length}</p>
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border border-border-subtle">
          <div className="flex items-center">
            <div className="p-3 bg-teal-50 text-secondary rounded-full">
              <Activity className="w-6 h-6" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-text-muted">Today's Total</p>
              <p className="text-2xl font-semibold text-text-navy">{todayCount}</p>
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow-sm border border-border-subtle">
          <div className="flex items-center">
            <div className="p-3 bg-green-50 text-success rounded-full">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-text-muted">Reviewed</p>
              <p className="text-2xl font-semibold text-text-navy">{reviewed.length}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow-sm border border-border-subtle">
        <div className="px-6 py-4 border-b border-border-subtle flex justify-between items-center">
          <h2 className="text-lg font-semibold text-text-navy">Priority Queue</h2>
          <button onClick={() => navigate('/reviews')} className="text-primary text-sm font-medium hover:underline">
            View All
          </button>
        </div>
        <div className="divide-y divide-border-subtle">
          {topPending.length === 0 ? (
            <div className="p-6 text-center text-text-muted">No pending reviews.</div>
          ) : (
            topPending.map(item => (
              <div 
                key={item.id}
                onClick={() => navigate(`/reviews/${item.id}`)}
                className="px-6 py-4 flex items-center justify-between hover:bg-gray-50 cursor-pointer transition-colors"
              >
                <div>
                  <div className="flex items-center gap-3">
                    <span className="font-medium text-text-navy">{item.patientName}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      item.urgency === 'urgent' ? 'bg-red-100 text-urgent' :
                      item.urgency === 'soon' ? 'bg-yellow-100 text-warning' :
                      'bg-blue-100 text-primary'
                    }`}>
                      {item.urgency?.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-sm text-text-muted mt-1 truncate max-w-md">{item.query}</p>
                </div>
                <div className="text-right">
                  <span className="text-sm text-text-muted">
                    {new Date(item.createdAt).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
