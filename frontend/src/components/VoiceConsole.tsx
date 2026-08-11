import { WebSession, type SessionStatus, type TranscriptEvent } from "@omnidim-ai/client";
import { useEffect, useRef, useState } from "react";
import { createVoiceSession, voiceStatus } from "../api";
import type { RadioEvent } from "../types";

type Line = { role: "user" | "agent"; text: string };

const PROMPTS = ["How is the driver?", "Can I talk to him?", "What should I say?", "Why do you think that?"];

/** The engineer's eyes are on the data — that is the whole premise of the problem.
 *  So the reading is also available hands-free, briefed on the call that is on screen. */
export default function VoiceConsole({ event }: { event: RadioEvent | null }) {
  const [available, setAvailable] = useState<boolean | null>(null);
  const [status, setStatus] = useState<SessionStatus>("connecting");
  const [live, setLive] = useState(false);
  const [muted, setMuted] = useState(false);
  const [lines, setLines] = useState<Line[]>([]);
  const [briefedOn, setBriefedOn] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sessionRef = useRef<WebSession | null>(null);

  useEffect(() => {
    voiceStatus()
      .then((s) => setAvailable(s.configured))
      .catch(() => setAvailable(false));
    return () => sessionRef.current?.stop();
  }, []);

  // A session that never reaches 'active' is almost always the microphone, and a
  // spinner that never resolves tells the user nothing.
  useEffect(() => {
    if (!live || status !== "connecting") return;
    const timer = setTimeout(
      () => setError("Still connecting — check that the browser has microphone permission for this page."),
      10000,
    );
    return () => clearTimeout(timer);
  }, [live, status]);

  async function connect() {
    setError(null);
    setLines([]);
    setStatus("connecting");
    setLive(true);

    try {
      const minted = await createVoiceSession(event?.id ?? null);
      setBriefedOn(minted.briefedOn);

      const session = new WebSession();
      sessionRef.current = session;

      session.on("status", (next) => {
        setStatus(next);
        if (typeof next === "object" && next.state === "ended") setLive(false);
      });
      session.on("transcript", (t: TranscriptEvent) => {
        if (!t.final) return;
        setLines((prev) => [...prev.slice(-7), { role: t.role, text: t.text }]);
      });
      session.on("error", (e) => setError(e.message));

      await session.start({ wsUrl: minted.wsUrl });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the voice session");
      setLive(false);
    }
  }

  function hangUp() {
    sessionRef.current?.stop();
    sessionRef.current = null;
    setLive(false);
  }

  function toggleMute() {
    const next = !muted;
    sessionRef.current?.mute(next);
    setMuted(next);
  }

  const label =
    status === "connecting" ? "Connecting" : status === "active" ? "Live" : `Ended · ${status.reason}`;

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-neutral-800 bg-neutral-900/40 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.15em] text-neutral-400">
          Pit wall voice
        </h2>
        {available === false ? (
          <span className="rounded bg-neutral-800 px-2 py-0.5 text-[10px] text-neutral-500">Not configured</span>
        ) : (
          live && (
            <span
              className={`flex items-center gap-1.5 rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                status === "active" ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/15 text-amber-300"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full bg-current ${status === "active" ? "animate-pulse" : ""}`} />
              {label}
            </span>
          )
        )}
      </div>

      {available === false ? (
        <p className="text-xs leading-relaxed text-neutral-500">
          Set <code className="text-neutral-400">OMNIDIM_API_KEY</code> in <code className="text-neutral-400">backend/.env</code> to
          enable the hands-free agent.
        </p>
      ) : (
        <>
          <p className="text-xs leading-relaxed text-neutral-500">
            Ask out loud instead of reading the screen. The agent is briefed server-side on the selected
            call, so it can only report what was actually measured.
          </p>

          <div className="flex flex-wrap items-center gap-2">
            {!live ? (
              <button
                onClick={connect}
                disabled={available === null}
                className="rounded bg-sky-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-sky-500 disabled:opacity-40"
              >
                Talk to pit wall
              </button>
            ) : (
              <>
                <button
                  onClick={hangUp}
                  className="rounded bg-red-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-red-500"
                >
                  Hang up
                </button>
                <button
                  onClick={toggleMute}
                  className="rounded border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 hover:bg-neutral-800"
                >
                  {muted ? "Unmute" : "Mute"}
                </button>
              </>
            )}
            {briefedOn && live && (
              <span className="text-[11px] text-neutral-600">briefed on lap {briefedOn}</span>
            )}
          </div>

          {!live && (
            <div className="flex flex-wrap gap-1.5">
              {PROMPTS.map((prompt) => (
                <span key={prompt} className="rounded bg-neutral-900 px-2 py-1 text-[11px] text-neutral-500">
                  "{prompt}"
                </span>
              ))}
            </div>
          )}

          {lines.length > 0 && (
            <div className="flex flex-col gap-1.5 rounded border border-neutral-800 bg-neutral-950 p-3">
              {lines.map((line, i) => (
                <p key={i} className="text-xs leading-relaxed">
                  <span className={line.role === "agent" ? "text-sky-400" : "text-neutral-500"}>
                    {line.role === "agent" ? "Pit wall" : "You"}
                  </span>
                  <span className="text-neutral-300"> · {line.text}</span>
                </p>
              ))}
            </div>
          )}
        </>
      )}

      {error && <p className="text-xs text-red-400">{error}</p>}
    </section>
  );
}
