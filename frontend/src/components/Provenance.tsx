import type { SessionPayload } from "../types";

/** Stated plainly because the two are not the same: the radio is real recorded
 *  audio, the lap times are not. Anything generated is labelled as generated. */
export default function Provenance({ session }: { session: SessionPayload["session"] }) {
  const provenance = session.provenance;
  if (!provenance) return null;

  const rows = [
    { label: "Radio audio", value: provenance.audio, real: !/synthetic|not set/i.test(provenance.audio) },
    { label: "Transcripts", value: provenance.transcripts, real: true },
    { label: "Lap times", value: provenance.lapTimes, real: !/synthetic|illustrative/i.test(provenance.lapTimes) },
    // The transcript sits on screen beside the reading, so a viewer can see for
    // themselves that many calls are the engineer. Say it before they notice it.
    {
      label: "Whose voice",
      value:
        "Broadcast team radio is one mixed channel. Many transmissions are the engineer speaking, " +
        "and some carry both voices in a single clip, so a reading describes the transmission rather " +
        "than the driver alone. Three attempts to separate the two were measured and all failed.",
      real: false,
    },
  ];

  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-5">
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.15em] text-neutral-400">Data provenance</h2>
      <dl className="mt-3 flex flex-col gap-2">
        {rows.map((row) => (
          <div key={row.label} className="grid grid-cols-[86px_1fr] items-start gap-3">
            <dt className="text-xs text-neutral-500">{row.label}</dt>
            <dd className="flex items-start gap-2 text-xs leading-relaxed text-neutral-300">
              <span
                className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${
                  row.real ? "bg-emerald-400" : "bg-amber-400"
                }`}
              />
              {row.value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
