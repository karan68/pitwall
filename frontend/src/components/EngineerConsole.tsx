import { useEffect, useState } from "react";
import { compose } from "../api";
import type { CompressResult, RadioEvent } from "../types";
import { WINDOW_STYLE } from "../theme";

const SAMPLE =
  "Okay so we're looking at plan B which is the two stop, we need you to push for three laps and then " +
  "we'll bring you in, and just watch the front left because it's degrading faster than we expected";

/** Radio brevity: the more loaded the driver, the fewer words they can absorb. */
export default function EngineerConsole({ event }: { event: RadioEvent | null }) {
  const [message, setMessage] = useState(SAMPLE);
  const [result, setResult] = useState<CompressResult | null>(null);
  const [speaking, setSpeaking] = useState(false);

  const budget = event?.recommendation.wordBudget ?? 26;
  const window_ = event?.recommendation.radioWindow ?? "Open";
  const style = WINDOW_STYLE[window_];

  useEffect(() => {
    if (!message.trim()) {
      setResult(null);
      return;
    }
    const timer = setTimeout(() => {
      compose(message, budget).then(setResult).catch(() => setResult(null));
    }, 250);
    return () => clearTimeout(timer);
  }, [message, budget]);

  function speak() {
    const text = result?.adapted ?? message;
    if (!text || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = window_ === "Closed" ? 0.95 : 1.05;
    utterance.onend = () => setSpeaking(false);
    setSpeaking(true);
    window.speechSynthesis.speak(utterance);
  }

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-neutral-800 bg-neutral-900/40 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.15em] text-neutral-400">
          Message to driver
        </h2>
        <span className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${style.bg} ${style.text}`}>
          Budget · {budget} words
        </span>
      </div>

      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        rows={3}
        className="w-full resize-none rounded border border-neutral-800 bg-neutral-950 p-3 text-sm leading-relaxed text-neutral-300 outline-none focus:border-neutral-600"
        placeholder="What you want to tell the driver…"
      />

      <div className="rounded border border-neutral-800 bg-neutral-950 p-3">
        <div className="mb-1.5 flex items-center justify-between">
          <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-neutral-600">As transmitted</p>
          {result?.changed && (
            <span className="text-[10px] text-neutral-500">
              −{result.removedWords} words
            </span>
          )}
        </div>
        <p className={`text-sm leading-relaxed ${result?.adapted ? "text-neutral-100" : "text-neutral-600"}`}>
          {result?.adapted || "—"}
        </p>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={speak}
          disabled={!result?.adapted}
          className="rounded bg-neutral-800 px-3 py-1.5 text-xs font-medium text-neutral-200 hover:bg-neutral-700 disabled:opacity-40"
        >
          {speaking ? "Speaking…" : "Transmit"}
        </button>
        <p className="text-[11px] text-neutral-600">
          {window_ === "Closed"
            ? "Window is closed — hold this unless it is safety-critical."
            : window_ === "Caution"
              ? "Keep it to the instruction. No justification."
              : "Full briefing is affordable right now."}
        </p>
      </div>
    </section>
  );
}
