import { useRef, useState } from "react";

interface Props {
  onAnalyze: (files: File[], startLap?: number) => Promise<void>;
  onCalibrate: (files: File[]) => Promise<void>;
  busy: boolean;
  baselineCount: number;
  samplesNeeded: number;
}

export default function RadioInput({ onAnalyze, onCalibrate, busy, baselineCount, samplesNeeded }: Props) {
  const [files, setFiles] = useState<File[]>([]);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [lap, setLap] = useState("");
  const [recording, setRecording] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  function accept(next: File[]) {
    // Filename order, so a stint exported as call_06..call_17 runs in sequence.
    const ordered = [...next].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
    setFiles(ordered);
    setAudioUrl(ordered.length === 1 ? URL.createObjectURL(ordered[0]) : null);
  }

  async function startRecording() {
    setMicError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        accept([new File([blob], `radio-${Date.now()}.webm`, { type: "audio/webm" })]);
        stream.getTracks().forEach((t) => t.stop());
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch {
      setMicError("Microphone unavailable.");
    }
  }

  function stopRecording() {
    recorderRef.current?.stop();
    setRecording(false);
  }

  const calibrating = samplesNeeded > 0;

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-neutral-800 bg-neutral-900/40 p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.15em] text-neutral-400">Radio in</h2>
        <span
          className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
            calibrating ? "bg-amber-500/15 text-amber-300" : "bg-emerald-500/15 text-emerald-300"
          }`}
        >
          {calibrating ? `Calibrating ${baselineCount}/${baselineCount + samplesNeeded}` : `Calibrated · ${baselineCount} clips`}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <input
          type="file"
          accept="audio/*"
          multiple
          onChange={(e) => accept(Array.from(e.target.files ?? []))}
          className="max-w-[220px] text-xs text-neutral-400 file:mr-2 file:rounded file:border-0 file:bg-neutral-800 file:px-3 file:py-1.5 file:text-xs file:text-neutral-200 hover:file:bg-neutral-700"
        />
        <button
          onClick={recording ? stopRecording : startRecording}
          className={`rounded px-3 py-1.5 text-xs font-medium ${
            recording ? "animate-pulse bg-red-600 text-white" : "bg-neutral-800 text-neutral-200 hover:bg-neutral-700"
          }`}
        >
          {recording ? "Stop" : "Record"}
        </button>
      </div>

      {audioUrl && <audio controls src={audioUrl} className="h-9 w-full" />}
      {files.length > 1 && (
        <p className="text-xs text-neutral-400">
          {files.length} clips queued, in filename order: {files[0].name} → {files[files.length - 1].name}
        </p>
      )}
      {micError && <p className="text-xs text-red-400">{micError}</p>}

      <div className="flex flex-wrap items-center gap-2 border-t border-neutral-800 pt-4">
        <button
          onClick={() => files.length && onCalibrate(files)}
          disabled={!files.length || busy}
          className="rounded border border-neutral-700 px-3 py-1.5 text-xs font-medium text-neutral-300 hover:bg-neutral-800 disabled:opacity-40"
          title="Register these clips as calm references for this driver"
        >
          {files.length > 1 ? `Add ${files.length} to baseline` : "Add to baseline"}
        </button>

        <div className="ml-auto flex items-center gap-2">
          <input
            type="number"
            min={1}
            value={lap}
            onChange={(e) => setLap(e.target.value)}
            placeholder={files.length > 1 ? "1st lap" : "Lap"}
            className="w-16 rounded border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-xs text-neutral-200"
          />
          <button
            onClick={() => files.length && onAnalyze(files, lap.trim() ? Number(lap) : undefined)}
            disabled={!files.length || busy}
            className="rounded bg-red-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-red-500 disabled:opacity-40"
          >
            {busy ? "Analysing…" : files.length > 1 ? `Analyse ${files.length} calls` : "Analyse call"}
          </button>
        </div>
      </div>

      {calibrating && (
        <p className="text-xs leading-relaxed text-amber-300/80">
          Add {samplesNeeded} more calm clip{samplesNeeded > 1 ? "s" : ""} from this driver. Until then, readings are
          scored against population averages rather than their own voice.
        </p>
      )}
    </section>
  );
}
