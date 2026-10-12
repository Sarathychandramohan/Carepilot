import { useState } from 'react';
import { useAuthStore } from '../services/authStore';
import toast from 'react-hot-toast';

export function SettingsPage() {
  const user = useAuthStore(state => state.user);
  const [emailNotifs, setEmailNotifs] = useState(true);
  const [pushNotifs, setPushNotifs] = useState(true);
  const [queueSort, setQueueSort] = useState('urgency');
  
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');

  const handlePasswordChange = (e: React.FormEvent) => {
    e.preventDefault();
    if (currentPassword && newPassword) {
      toast.success('Password changed successfully');
      setCurrentPassword('');
      setNewPassword('');
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <h1 className="text-2xl font-bold text-text-navy mb-6">Settings</h1>

      <div className="bg-white p-6 rounded-lg shadow-sm border border-border-subtle">
        <h2 className="text-lg font-semibold text-text-navy mb-4 border-b border-border-subtle pb-2">Account Profile</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-text-muted mb-1">Full Name</label>
            <div className="text-text-navy font-medium bg-gray-50 p-2 rounded border border-border-subtle">{user?.name}</div>
          </div>
          <div>
            <label className="block text-sm font-medium text-text-muted mb-1">Email</label>
            <div className="text-text-navy font-medium bg-gray-50 p-2 rounded border border-border-subtle">{user?.email}</div>
          </div>
          <div>
            <label className="block text-sm font-medium text-text-muted mb-1">Specialization</label>
            <div className="text-text-navy font-medium bg-gray-50 p-2 rounded border border-border-subtle">{user?.specialization}</div>
          </div>
        </div>
      </div>

      <div className="bg-white p-6 rounded-lg shadow-sm border border-border-subtle">
        <h2 className="text-lg font-semibold text-text-navy mb-4 border-b border-border-subtle pb-2">Preferences</h2>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-medium text-text-navy">Email Notifications</h3>
              <p className="text-sm text-text-muted">Receive daily summaries and urgent alerts via email.</p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" checked={emailNotifs} onChange={e => setEmailNotifs(e.target.checked)} className="sr-only peer" />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
            </label>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-medium text-text-navy">Push Notifications</h3>
              <p className="text-sm text-text-muted">Receive browser notifications for new reviews.</p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" checked={pushNotifs} onChange={e => setPushNotifs(e.target.checked)} className="sr-only peer" />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
            </label>
          </div>
          
          <div className="pt-4 border-t border-border-subtle">
            <label className="block text-sm font-medium text-text-navy mb-2">Default Queue Sort Order</label>
            <select 
              value={queueSort} 
              onChange={e => setQueueSort(e.target.value)}
              className="w-full md:w-1/2 border-border-subtle rounded-md shadow-sm focus:border-primary focus:ring-primary py-2 px-3 border text-black"
            >
              <option value="urgency">Highest Urgency First</option>
              <option value="newest">Newest First</option>
              <option value="oldest">Oldest First</option>
            </select>
          </div>
        </div>
      </div>

      <div className="bg-white p-6 rounded-lg shadow-sm border border-border-subtle">
        <h2 className="text-lg font-semibold text-text-navy mb-4 border-b border-border-subtle pb-2">Security</h2>
        <form onSubmit={handlePasswordChange} className="space-y-4 max-w-md">
          <div>
            <label className="block text-sm font-medium text-text-navy mb-1">Current Password</label>
            <input 
              type="password" 
              value={currentPassword}
              onChange={e => setCurrentPassword(e.target.value)}
              className="w-full border-border-subtle rounded-md shadow-sm focus:border-primary focus:ring-primary py-2 px-3 border text-black" 
              required 
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-text-navy mb-1">New Password</label>
            <input 
              type="password" 
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              className="w-full border-border-subtle rounded-md shadow-sm focus:border-primary focus:ring-primary py-2 px-3 border text-black" 
              required 
            />
          </div>
          <button type="submit" className="px-4 py-2 bg-primary text-white rounded-md hover:bg-blue-700 font-medium transition-colors">
            Update Password
          </button>
        </form>
      </div>

    </div>
  );
}
