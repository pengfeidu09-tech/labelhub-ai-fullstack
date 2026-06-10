import { create } from 'zustand';

interface AppState {
  currentRole: 'owner' | 'labeler' | 'reviewer' | null;
  setCurrentRole: (role: 'owner' | 'labeler' | 'reviewer' | null) => void;
  isConnected: boolean;
  setIsConnected: (connected: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  currentRole: null,
  setCurrentRole: (role) => set({ currentRole: role }),
  isConnected: false,
  setIsConnected: (connected) => set({ isConnected: connected }),
}));
