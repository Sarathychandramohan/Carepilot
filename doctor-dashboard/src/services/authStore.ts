import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { Doctor } from '../types';

interface AuthState {
  user: Doctor | null;
  login: () => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      login: () => set({ 
        user: { 
          id: 'doc-001', 
          name: 'Dr. Amelia Smith', 
          specialization: 'Nephrology', 
          email: 'doctor@carepilot.ai' 
        } 
      }),
      logout: () => set({ user: null }),
    }),
    {
      name: 'carepilot:auth',
      storage: createJSONStorage(() => localStorage)
    }
  )
);
