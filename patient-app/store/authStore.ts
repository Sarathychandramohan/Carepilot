import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { HERO_PATIENT } from '../services/mock/mockData';
import { Patient } from '../types';

interface AuthState {
  user: Patient | null;
  isAuthenticated: boolean;
  login: (email: string, pass: string) => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      login: async (email, pass) => {
        if (email === 'patient@carepilot.ai' && pass === 'demo1234') {
          set({ user: HERO_PATIENT, isAuthenticated: true });
        } else {
          throw new Error('Invalid credentials');
        }
      },
      logout: () => set({ user: null, isAuthenticated: false })
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => AsyncStorage)
    }
  )
);
