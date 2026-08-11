import { useEffect, useState } from "react";
import { addBaselineClip, analyzeClip, fetchSession, resetBaseline, resetSession } from "./api";
import AdvisorPanel from "./components/AdvisorPanel";
import EngineerConsole from "./components/EngineerConsole";
import LoadLapChart from "./components/LoadLapChart";
import QuadrantChart from "./components/QuadrantChart";
import RadioInput from "./components/RadioInput";
import RadioLog from "./components/RadioLog";
import ReferenceCompare from "./components/ReferenceCompare";
import StateBreakdown from "./components/StateBreakdown";
import StatusStrip from "./components/StatusStrip";
import VoiceConsole from "./components/VoiceConsole";
import type { RadioEvent, SessionPayload } from "./types";

export default function App() {
  const [session, setSession] = useState<SessionPayload | null>(null);
  const [selected, setSelected] = useState<RadioEvent | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    fetchSession()
      .then(setSession)
      .catch((e) => setError(e instanceof Error ? e.message : "Backend unreachable"));
  }, []);

  async function run<T>(action: () => Promise<T>, onDone: (result: T) => void) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      onDone(await action());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const handleAnalyze = (file: File, lap?: number) =>
    run(
      () => analyzeClip(file, file.name, lap),
      (payload) => {
        setSession(payload);
        setSelected(payload.event ?? null);
      },
    );

  const handleCalibrate = (file: File) =>
    run(
      () => addBaselineClip(file, file.name),
      (payload) => {
        setSession(payload);
        setNotice(
          payload.baseline.calibrated
            ? `Baseline set from ${payload.baseline.sampleCount} clips. Readings are now driver-relative.`
            : `Baseline clip added (${payload.baseline.sampleCount}). ${payload.baseline.samplesNeeded} more needed.`,
        );
      },
    );

  const analytics = session?.analytics;

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-200">
      <header className="flex flex-wrap items-center justify-between gap-4 px-6 py-4">
        <div className="flex items-baseline gap-4">
          <h1 className="text-xl font-bold tracking-[0.2em] text-neutral-50">PITWALL</h1>
          <p className="text-xs text-neutral-500">
            The Silent Co-Driver — driver state from radio, and the call that follows
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs text-neutral-500">
          {session && (
            <span className="tabular-nums">
              {session.session.driver} · {session.session.stint}
            </span>
          )}
          <button
            onClick={() => run(resetSession, (p) => (setSession(p), setSelected(null)))}
            className="rounded border border-neutral-800 px-2.5 py-1 hover:bg-neutral-900"
          >
            Clear stint
          </button>
          <button
            onClick={() => run(resetBaseline, setSession)}
            className="rounded border border-neutral-800 px-2.5 py-1 hover:bg-neutral-900"
          >
            Clear baseline
          </button>
        </div>
      </header>

      <StatusStrip event={selected} />

      {(error || notice) && (
        <div
          className={`px-6 py-2 text-xs ${
            error ? "bg-red-950/40 text-red-300" : "bg-emerald-950/30 text-emerald-300"
          }`}
        >
          {error ?? notice}
        </div>
      )}

      <main className="mx-auto grid max-w-[1400px] gap-4 px-6 py-5 lg:grid-cols-2">
        <div className="flex flex-col gap-4">
          <RadioInput
            onAnalyze={handleAnalyze}
            onCalibrate={handleCalibrate}
            busy={busy}
            baselineCount={session?.baseline.sampleCount ?? 0}
            samplesNeeded={session?.baseline.samplesNeeded ?? 3}
          />

          {selected && <Transcript event={selected} />}
          {selected && <AdvisorPanel event={selected} />}
          <EngineerConsole event={selected} />
          <VoiceConsole event={selected} />
        </div>

        <div className="flex flex-col gap-4">
          {selected && <StateBreakdown event={selected} />}
          {session && session.events.length > 0 && (
            <QuadrantChart events={session.events} selectedId={selected?.id ?? null} />
          )}
          {analytics && <LoadLapChart analytics={analytics} events={session!.events} />}
          {analytics?.sufficientData && <CostSummary analytics={analytics} />}
          {selected && <ReferenceCompare event={selected} />}
        </div>

        <div className="lg:col-span-2">
          <RadioLog
            events={session?.events ?? []}
            selectedId={selected?.id ?? null}
            onSelect={setSelected}
          />
        </div>
      </main>
    </div>
  );
}

function Transcript({ event }: { event: RadioEvent }) {
  const { quality } = event;
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.15em] text-neutral-400">
          Lap {event.lap} · transcript
        </h2>
        <span
          className={`rounded px-2 py-0.5 text-[10px] font-medium ${
            quality.usable ? "bg-neutral-800 text-neutral-400" : "bg-amber-500/15 text-amber-300"
          }`}
          title={quality.issues.join(" ")}
        >
          {quality.usable ? `SNR ${quality.snrDb} dB` : "Audio quality warning"}
        </span>
      </div>
      <p className="mt-2 text-lg leading-snug text-neutral-100">
        {event.transcript || <span className="text-neutral-600">(no speech detected)</span>}
      </p>
      {!quality.usable && (
        <ul className="mt-2 list-disc pl-4 text-[11px] leading-relaxed text-amber-300/80">
          {quality.issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function CostSummary({ analytics }: { analytics: NonNullable<SessionPayload["analytics"]> }) {
  const cells = [
    { label: "Time lost to driver load", value: `${analytics.estimatedSecondsLost}s`, accent: true },
    { label: "Laps above threshold", value: `${analytics.lapsAffected}` },
    {
      label: "Warning lead time",
      value: analytics.lagLaps ? `${analytics.lagLaps} lap${analytics.lagLaps > 1 ? "s" : ""}` : "same lap",
    },
    { label: "Radio calls", value: `${analytics.sampleSize}` },
  ];

  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5">
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.15em] text-neutral-400">Stint cost</h2>
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {cells.map((cell) => (
          <div key={cell.label}>
            <p className={`text-xl font-semibold tabular-nums ${cell.accent ? "text-red-300" : "text-neutral-200"}`}>
              {cell.value}
            </p>
            <p className="mt-0.5 text-[10px] leading-tight text-neutral-500">{cell.label}</p>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[11px] leading-relaxed text-neutral-600">
        Estimated from the fitted slope of lap-time delta against driver load. Indicative for this stint only.
      </p>
    </section>
  );
}
