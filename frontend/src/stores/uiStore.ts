import { create } from "zustand";

interface UIState {
  showExplorer: boolean;
  showDrawer: boolean;
  drawerTab: "history" | "memory" | "context";
  drawerFocusSearch: boolean;
  drawerAutoPreview: boolean;
  showPalette: boolean;
  showTutorial: boolean;
  showSnake: boolean;
  showQuickSettings: boolean;
  showMentalModel: boolean;

  setShowExplorer: (v: boolean) => void;
  setShowDrawer: (v: boolean) => void;
  setDrawerTab: (v: "history" | "memory" | "context") => void;
  setDrawerFocusSearch: (v: boolean) => void;
  setDrawerAutoPreview: (v: boolean) => void;
  setShowPalette: (v: boolean) => void;
  setShowTutorial: (v: boolean) => void;
  setShowSnake: (v: boolean) => void;
  setShowQuickSettings: (v: boolean) => void;
  setShowMentalModel: (v: boolean) => void;
  togglePalette: () => void;
  toggleTutorial: () => void;
  closeAllOverlays: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  showExplorer: false,
  showDrawer: false,
  drawerTab: "history",
  drawerFocusSearch: false,
  drawerAutoPreview: false,
  showPalette: false,
  showTutorial: false,
  showSnake: false,
  showQuickSettings: false,
  showMentalModel: false,

  setShowExplorer: (v) => set({ showExplorer: v }),
  setShowDrawer: (v) => set({ showDrawer: v }),
  setDrawerTab: (v) => set({ drawerTab: v }),
  setDrawerFocusSearch: (v) => set({ drawerFocusSearch: v }),
  setDrawerAutoPreview: (v) => set({ drawerAutoPreview: v }),
  setShowPalette: (v) => set({ showPalette: v }),
  setShowTutorial: (v) => set({ showTutorial: v }),
  setShowSnake: (v) => set({ showSnake: v }),
  setShowQuickSettings: (v) => set({ showQuickSettings: v }),
  setShowMentalModel: (v) => set({ showMentalModel: v }),
  togglePalette: () => set((s) => ({ showPalette: !s.showPalette })),
  toggleTutorial: () => set((s) => ({ showTutorial: !s.showTutorial })),
  closeAllOverlays: () =>
    set({
      showExplorer: false,
      showDrawer: false,
      showPalette: false,
      showTutorial: false,
      showSnake: false,
      showQuickSettings: false,
      showMentalModel: false,
    }),
}));
