import { create } from 'zustand'

type Panel = 'chats' | 'notifications' | 'account' | null
type ShellState = { panel: Panel; togglePanel: (panel: Exclude<Panel, null>) => void; closePanel: () => void }
export const useShellStore = create<ShellState>((set) => ({
  panel: null,
  togglePanel: (panel) => set((state) => ({ panel: state.panel === panel ? null : panel })),
  closePanel: () => set({ panel: null }),
}))
