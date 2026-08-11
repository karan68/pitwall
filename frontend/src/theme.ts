import type { DriverState, RadioWindow } from "./types";

export const STATE_STYLE: Record<DriverState, { text: string; bg: string; border: string; dot: string }> = {
  Calm: {
    text: "text-emerald-300",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/40",
    dot: "#34d399",
  },
  "Locked In": {
    text: "text-sky-300",
    bg: "bg-sky-500/10",
    border: "border-sky-500/40",
    dot: "#38bdf8",
  },
  Stressed: {
    text: "text-red-300",
    bg: "bg-red-500/10",
    border: "border-red-500/40",
    dot: "#f87171",
  },
  Tired: {
    text: "text-amber-300",
    bg: "bg-amber-500/10",
    border: "border-amber-500/40",
    dot: "#fbbf24",
  },
};

export const WINDOW_STYLE: Record<RadioWindow, { text: string; bg: string; border: string; label: string }> = {
  Open: {
    text: "text-emerald-300",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/50",
    label: "SAFE TO TALK",
  },
  Caution: {
    text: "text-amber-300",
    bg: "bg-amber-500/10",
    border: "border-amber-500/50",
    label: "KEEP IT SHORT",
  },
  Closed: {
    text: "text-red-300",
    bg: "bg-red-500/10",
    border: "border-red-500/50",
    label: "DO NOT TRANSMIT",
  },
};

export const BIOMARKER_LABELS: Record<string, { label: string; unit: string; meaning: string }> = {
  f0MeanHz: { label: "Pitch", unit: "Hz", meaning: "Rises with arousal" },
  energyDb: { label: "Loudness", unit: "dB", meaning: "Rises with vocal effort" },
  articulationRate: { label: "Speech rate", unit: "w/s", meaning: "Rises under time pressure" },
  highFreqRatio: { label: "Vocal effort", unit: "", meaning: "High-frequency energy share" },
  jitterPct: { label: "Pitch instability", unit: "%", meaning: "Cycle-to-cycle pitch variation" },
  shimmerPct: { label: "Volume instability", unit: "%", meaning: "Cycle-to-cycle amplitude variation" },
  hnrDb: { label: "Voice clarity", unit: "dB", meaning: "Falls as the voice strains" },
  pauseRatio: { label: "Pausing", unit: "", meaning: "Rises with fatigue" },
};
