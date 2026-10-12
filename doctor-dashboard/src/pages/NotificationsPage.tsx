import { useWorkflowStore } from '../services/mock/mockWorkflow';
import { cn } from '../utils/cn';
import { Bell, Calendar, MessageSquare, Check } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export function NotificationsPage() {
  const notifications = useWorkflowStore(state => state.doctorNotifications);
  const markNotificationRead = useWorkflowStore(state => state.markNotificationRead);
  const markAllNotificationsRead = useWorkflowStore(state => state.markAllNotificationsRead);
  const navigate = useNavigate();

  const sortedNotifications = [...notifications].sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

  const handleNotificationClick = (n: typeof notifications[0]) => {
    markNotificationRead(n.id);
    if (n.category === 'consultation' && n.relatedId) {
      navigate(`/reviews/${n.relatedId}`);
    } else if (n.category === 'appointment') {
      navigate('/appointments');
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-text-navy">Notifications</h1>
        {notifications.some(n => !n.read) && (
          <button 
            onClick={markAllNotificationsRead}
            className="text-sm font-medium text-primary hover:text-blue-700 flex items-center"
          >
            <Check className="w-4 h-4 mr-1" /> Mark all as read
          </button>
        )}
      </div>

      {sortedNotifications.length === 0 ? (
        <div className="p-12 text-center bg-white rounded-lg border border-border-subtle text-text-muted">
          You're all caught up. No notifications.
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-border-subtle divide-y divide-border-subtle overflow-hidden">
          {sortedNotifications.map(n => (
            <div 
              key={n.id} 
              onClick={() => handleNotificationClick(n)}
              className={cn(
                "p-4 flex items-start cursor-pointer hover:bg-gray-50 transition-colors",
                !n.read ? "bg-blue-50/50 border-l-4 border-l-primary" : "border-l-4 border-l-transparent"
              )}
            >
              <div className={cn(
                "p-2 rounded-full mr-4 shrink-0",
                n.category === 'consultation' ? "bg-purple-100 text-purple-600" :
                n.category === 'appointment' ? "bg-green-100 text-success" : "bg-gray-100 text-text-muted"
              )}>
                {n.category === 'consultation' ? <MessageSquare className="w-5 h-5" /> :
                 n.category === 'appointment' ? <Calendar className="w-5 h-5" /> :
                 <Bell className="w-5 h-5" />}
              </div>
              <div className="flex-1">
                <div className="flex justify-between items-start">
                  <h3 className={cn("text-sm", !n.read ? "font-bold text-text-navy" : "font-medium text-text-navy")}>
                    {n.title}
                  </h3>
                  <span className="text-xs text-text-muted whitespace-nowrap ml-4">
                    {new Date(n.createdAt).toLocaleString()}
                  </span>
                </div>
                <p className={cn("text-sm mt-1", !n.read ? "text-text-navy" : "text-text-muted")}>
                  {n.body}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
