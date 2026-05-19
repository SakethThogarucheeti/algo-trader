"use client";

import { create } from "zustand";

interface DashboardStore {
  sessionId: string;
  symbol: string;
  interval: string;
  setSessionId: (id: string) => void;
  setSymbol: (s: string) => void;
  setInterval: (i: string) => void;
}

export const useDashboardStore = create<DashboardStore>((set) => ({
  sessionId: "",
  symbol: "INFY",
  interval: "5min",
  setSessionId: (id) => set({ sessionId: id }),
  setSymbol: (s) => set({ symbol: s }),
  setInterval: (i) => set({ interval: i }),
}));
