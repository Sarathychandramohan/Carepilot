import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Inbox, Users, Calendar, BarChart2, Bell, Settings, LogOut, Activity } from 'lucide-react';
import { useAuthStore } from '../../services/authStore';
import { useWorkflowStore } from '../../services/mock/mockWorkflow';
import { cn } from '../../utils/cn';

export function Sidebar() {
  const logout = useAuthStore(state => state.logout);
  const user = useAuthStore(state => state.user);
  const consultations = useWorkflowStore(state => state.consultations);
  const pendingCount = consultations.filter(c => c.status === 'doctor_review').length;

  const navItems = [
    { icon: LayoutDashboard, label: 'Dashboard', to: '/dashboard' },
    { icon: Inbox, label: 'Review Queue', to: '/reviews', badge: pendingCount },
    { icon: Users, label: 'Patients', to: '/patients' },
    { icon: Calendar, label: 'Appointments', to: '/appointments' },
    { icon: BarChart2, label: 'Analytics', to: '/analytics' },
    { icon: Bell, label: 'Notifications', to: '/notifications' },
    { icon: Settings, label: 'Settings', to: '/settings' },
  ];

  return (
    <div className="fixed inset-y-0 left-0 w-64 bg-white border-r border-border-subtle flex flex-col z-10">
      <div className="h-16 flex items-center px-6 border-b border-border-subtle">
        <Activity className="h-8 w-8 text-primary mr-2" />
        <span className="text-xl font-bold text-text-navy">CarePilot AI</span>
      </div>
      
      <nav className="flex-1 overflow-y-auto py-4">
        <ul className="space-y-1 px-3">
          {navItems.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) => cn(
                  "flex items-center justify-between px-3 py-2 rounded-md transition-colors",
                  isActive 
                    ? "bg-primary/10 text-primary font-medium" 
                    : "text-text-muted hover:bg-bg-app hover:text-text-navy"
                )}
              >
                <div className="flex items-center">
                  <item.icon className="h-5 w-5 mr-3" />
                  {item.label}
                </div>
                {item.badge !== undefined && item.badge > 0 && (
                  <span className="bg-urgent text-white text-xs font-bold px-2 py-0.5 rounded-full">
                    {item.badge}
                  </span>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="p-4 border-t border-border-subtle">
        <div className="flex items-center justify-between mb-4 px-2">
          <div className="flex flex-col">
            <span className="text-sm font-medium text-text-navy truncate w-32">{user?.name}</span>
            <span className="text-xs text-text-muted truncate w-32">{user?.specialization}</span>
          </div>
          <button 
            onClick={logout}
            className="p-2 text-text-muted hover:text-urgent hover:bg-bg-app rounded-md transition-colors"
            title="Log out"
          >
            <LogOut className="h-5 w-5" />
          </button>
        </div>
      </div>
    </div>
  );
}
