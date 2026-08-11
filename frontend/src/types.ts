export interface LapEntry {
  lap: number;
  timeSeconds: number;
}

export type MoodLabel = "Calm" | "Stressed" | "Tired";

export interface RadioEvent {
  id: number;
  lap: number;
  fileName: string;
  transcript: string;
  label: MoodLabel;
  rawEmotion: string;
  confidence: number;
  stressIndex: number;
  breakdown: Record<string, number>;
}

export interface RaceState {
  baseLapSeconds: number;
  laps: LapEntry[];
  events: RadioEvent[];
}

export interface AnalyzeResponse {
  event: RadioEvent;
  laps: LapEntry[];
  events: RadioEvent[];
}
