export type DriverState = "Calm" | "Locked In" | "Stressed" | "Tired";
export type RadioWindow = "Open" | "Caution" | "Closed";

export interface Biomarkers {
  durationSeconds: number;
  f0MeanHz: number;
  f0StdHz: number;
  energyDb: number;
  jitterPct: number;
  shimmerPct: number;
  hnrDb: number;
  highFreqRatio: number;
  pauseRatio: number;
  voicedRatio: number;
  articulationRate: number;
}

export interface SignalQuality {
  snrDb: number;
  peakLevel: number;
  clippedRatio: number;
  voicedRatio: number;
  usable: boolean;
  issues: string[];
}

export interface ContentReading {
  intent: string;
  intentConfidence: number;
  hazardTerms: string[];
  downplaying: boolean;
  priority: "Critical" | "Strategic" | "Informational";
}

export interface Flag {
  level: "warning" | "info";
  title: string;
  detail: string;
}

export interface Recommendation {
  radioWindow: RadioWindow;
  windowReason: string;
  wordBudget: number;
  action: { headline: string; rationale: string };
  flags: Flag[];
}

export interface ReferenceReading {
  model: string;
  state: DriverState;
  rawLabel: string;
  confidence: number;
  breakdown: Record<string, number>;
}

export interface RadioEvent {
  id: number;
  lap: number;
  fileName: string;
  transcript: string;
  quality: SignalQuality;
  biomarkers: Biomarkers;
  content: ContentReading;
  reference: ReferenceReading;
  referenceDisagrees: boolean;
  state: DriverState;
  description: string;
  arousal: number;
  strain: number;
  driverLoad: number;
  zScores: Record<string, number>;
  calibrated: boolean;
  confidence: { level: string; reason: string };
  drivers: { feature: string; z: number; direction: string }[];
  recommendation: Recommendation;
}

export interface Baseline {
  calibrated: boolean;
  sampleCount: number;
  samplesNeeded: number;
  stats: Record<string, { centre: number; spread: number }>;
}

export interface LoadPoint {
  lap: number;
  timeSeconds: number;
  load: number | null;
  measured: boolean;
}

export interface Analytics {
  series: LoadPoint[];
  sufficientData: boolean;
  sampleSize: number;
  note: string;
  correlation?: number;
  lagLaps?: number;
  strength?: string;
  secondsPerLoadPoint?: number;
  estimatedSecondsLost?: number;
  lapsAffected?: number;
}

export interface SessionPayload {
  session: {
    driver: string;
    team: string;
    stint: string;
    referenceLapSeconds: number;
  };
  laps: { lap: number; timeSeconds: number }[];
  events: RadioEvent[];
  baseline: Baseline;
  analytics: Analytics;
  event?: RadioEvent;
}

export interface CompressResult {
  original: string;
  adapted: string;
  removedWords: number;
  changed: boolean;
}
