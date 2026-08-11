import { useEffect, useRef, useState } from "react";
import { analyzeClip, fetchState, resetEvents } from "./api";
import LapChart from "./components/LapChart";
import MoodBadge from "./components/MoodBadge";
import TranscriptCard from "./components/TranscriptCard";
import type { RaceState, RadioEvent } from "./types";

export default function App() {
  const [state, setState] = useState<RaceState | null>(null);
  const [lastEvent, setLastEvent] = useState<RadioEvent | null>(null);
  const [lapInput, setLapInput] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  useEffect(() => {
    fetchState()
      .then(setState)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load lap data"));
  }, []);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setAudioUrl(f ? URL.createObjectURL(f) : null);
  }

  async function startRecording() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        const recordedFile = new File([blob], `recording-${Date.now()}.webm`, { type: "audio/webm" });
        setFile(recordedFile);
        setAudioUrl(URL.createObjectURL(blob));
        stream.getTracks().forEach((t) => t.stop());
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setRecording(true);
    } catch {
      setError("Could not access the microphone.");
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  }

  async function handleAnalyze() {
    if (!file) {
      setError("Record or upload a radio clip first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const lap = lapInput.trim() ? Number(lapInput) : undefined;
      const result = await analyzeClip(file, file.name, lap);
      setLastEvent(result.event);
      setState((prev) => (prev ? { ...prev, events: result.events } : prev));
      setLapInput("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  async function handleReset() {
    const fresh = await resetEvents();
    setState(fresh);
    setLastEvent(null);
  }

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 px-6 py-5">
        <p className="text-xs font-semibold uppercase tracking-widest text-red-500">
          Grand Prix · AI Race Month
        </p>
        <h1 className="text-2xl font-bold">The Silent Co-Driver</h1>
        <p className="text-sm text-neutral-400">Reading driver stress from radio calls, lap by lap.</p>
      </header>

      <main className="mx-auto grid max-w-5xl gap-6 px-6 py-8 lg:grid-cols-2">
        <section className="flex flex-col gap-4 rounded-xl border border-neutral-800 bg-neutral-900/40 p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-400">1. Radio call</h2>

          <div className="flex flex-wrap items-center gap-3">
            <input
              type="file"
              accept="audio/*"
              onChange={handleFileChange}
              className="text-sm text-neutral-300 file:mr-3 file:rounded-lg file:border-0 file:bg-neutral-800 file:px-3 file:py-1.5 file:text-neutral-200"
            />
            {!recording ? (
              <button onClick={startRecording} className="rounded-lg bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700">
                🎙 Record
              </button>
            ) : (
              <button onClick={stopRecording} className="animate-pulse rounded-lg bg-red-600 px-3 py-1.5 text-sm">
                ⏹ Stop
              </button>
            )}
          </div>

          {audioUrl && <audio controls src={audioUrl} className="w-full" />}

          <div className="flex items-center gap-3">
            <label className="text-sm text-neutral-400">Lap #</label>
            <input
              type="number"
              min={1}
              value={lapInput}
              onChange={(e) => setLapInput(e.target.value)}
              placeholder="auto"
              className="w-24 rounded-lg border border-neutral-700 bg-neutral-800 px-2 py-1 text-sm"
            />
            <button
              onClick={handleAnalyze}
              disabled={busy}
              className="ml-auto rounded-lg bg-red-600 px-4 py-1.5 text-sm font-semibold hover:bg-red-500 disabled:opacity-50"
            >
              {busy ? "Analyzing…" : "Analyze"}
            </button>
          </div>

          {error && <p className="text-sm text-red-400">{error}</p>}

          {lastEvent && (
            <div className="flex flex-col gap-4 border-t border-neutral-800 pt-4">
              <TranscriptCard event={lastEvent} />
              <MoodBadge event={lastEvent} />
            </div>
          )}
        </section>

        <section className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-400">2. Lap time vs mood</h2>
            <button onClick={handleReset} className="text-xs text-neutral-500 hover:text-neutral-300">
              Reset session
            </button>
          </div>

          {state && <LapChart laps={state.laps} events={state.events} />}

          <div className="flex flex-col gap-2 rounded-xl border border-neutral-800 bg-neutral-900/40 p-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">Session log</h3>
            {state?.events.length ? (
              <ul className="flex flex-col gap-2 text-sm">
                {[...state.events].reverse().map((ev) => (
                  <li key={ev.id} className="flex items-center justify-between gap-2 rounded-lg bg-neutral-900 px-3 py-2">
                    <span className="text-neutral-400">Lap {ev.lap}</span>
                    <span className="truncate px-2 text-neutral-200">{ev.transcript}</span>
                    <span
                      className={
                        ev.label === "Stressed"
                          ? "text-red-400"
                          : ev.label === "Tired"
                            ? "text-amber-400"
                            : "text-emerald-400"
                      }
                    >
                      {ev.label}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-neutral-500">No radio calls analyzed yet this session.</p>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
