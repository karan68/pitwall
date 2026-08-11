import { useRef, useState } from "react";

interface Props {
  onAnalyze: (file: File, lap?: number) => Promise<void>;
  onCalibrate: (file: File) => Promise<void>;
  busy: boolean;
  baselineCount: number;
  samplesNeeded: number;
}

export default function RadioInput({ onAnalyze, onCalibrate, busy, baselineCount, samplesNeeded }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [lap, setLap] = useState("");
  const [recording, setRecording] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  function accept(next: File | null) {
    setFile(next);
    setAudioUrl(next ? URL.createObjectURL(next) : null);
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
        accept(new File([blob], `radio-${Date.now()}.webm`, { type: "audio/webm" }));
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
          onChange={(e) => accept(e.target.files?.[0] ?? null)}
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
      {micError && <p className="text-xs text-red-400">{micError}</p>}

      <div className="flex flex-wrap items-center gap-2 border-t border-neutral-800 pt-4">
        <button
          onClick={() => file && onCalibrate(file)}
          disabled={!file || busy}
          className="rounded border border-neutral-700 px-3 py-1.5 text-xs font-medium text-neutral-300 hover:bg-neutral-800 disabled:opacity-40"
          title="Register this clip as a calm reference for this driver"
        >
          Add to baseline
        </button>

        <div className="ml-auto flex items-center gap-2">
          <input
            type="number"
            min={1}
            value={lap}
            onChange={(e) => setLap(e.target.value)}
            placeholder="Lap"
            className="w-16 rounded border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-xs text-neutral-200"
          />
          <button
            onClick={() => file && onAnalyze(file, lap.trim() ? Number(lap) : undefined)}
            disabled={!file || busy}
            className="rounded bg-red-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-red-500 disabled:opacity-40"
          >
            {busy ? "Analysing…" : "Analyse call"}
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
