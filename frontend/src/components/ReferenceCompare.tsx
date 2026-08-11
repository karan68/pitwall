import type { RadioEvent } from "../types";
import { STATE_STYLE } from "../theme";

/** Kept visible on purpose: the off-the-shelf emotion classifier is what this problem
 *  is usually solved with, and showing where it disagrees is the argument for not
 *  stopping there. */
export default function ReferenceCompare({ event }: { event: RadioEvent }) {
  const { reference, referenceDisagrees } = event;

  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.15em] text-neutral-400">
          Cross-check: emotion classifier
        </h2>
        <span
          className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
            referenceDisagrees ? "bg-amber-500/15 text-amber-300" : "bg-neutral-800 text-neutral-400"
          }`}
        >
          {referenceDisagrees ? "Disagrees" : "Agrees"}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <div className="rounded border border-neutral-800 bg-neutral-950 p-3">
          <p className="text-[10px] uppercase tracking-wider text-neutral-600">Biomarkers say</p>
          <p className={`mt-0.5 text-lg font-semibold ${STATE_STYLE[event.state].text}`}>{event.state}</p>
          <p className="text-[10px] text-neutral-600">measured against this driver</p>
        </div>
        <div className="rounded border border-neutral-800 bg-neutral-950 p-3">
          <p className="text-[10px] uppercase tracking-wider text-neutral-600">Classifier says</p>
          <p className="mt-0.5 text-lg font-semibold text-neutral-300">{reference.state}</p>
          <p className="text-[10px] text-neutral-600">
            {reference.rawLabel} · {reference.confidence}%
          </p>
        </div>
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-neutral-500">
        {referenceDisagrees
          ? "The classifier is trained on acted emotional speech. Race radio is task speech under physical load, so it can be confidently wrong here — which is why the decision above is driven by measured biomarkers, not by this label."
          : "Both readings agree on this call. The biomarkers still carry the detail the classifier cannot: how far from normal, and in which direction."}
      </p>
    </section>
  );
}
