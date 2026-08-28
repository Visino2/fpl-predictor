import type { ChipRecommendation, ChipTimingSuggestion } from "../types/fpl";

interface ChipPanelProps {
  chips: ChipRecommendation[];
  timing: ChipTimingSuggestion[];
}

const CHIP_ICON: Record<string, string> = {
  "Bench Boost": "🔋",
  "Triple Captain": "⭐",
};

export default function ChipPanel({ chips, timing }: ChipPanelProps) {
  if (chips.length === 0) return null;

  const shown = timing.slice(0, 4);
  // The "best gameweek" list ranks weeks against each other; worth_playing is
  // the absolute bar. If even the top-ranked week is below the bar, nothing
  // clears it — spell that out so the list doesn't read as "play it now"
  // against a "hold" verdict card above.
  const topNotWorth = shown.length > 0 && !shown[0].worth_playing;

  return (
    <section className="flex flex-col gap-3">
      <h2 className="font-heading text-sm font-bold text-white/90">Chip Advice</h2>

      {chips.map((chip) => (
        <div
          key={chip.chip}
          className={`rounded-2xl border-l-4 bg-white/5 p-3 shadow-sm transition-colors hover:bg-white/[0.07] ${
            chip.recommend ? "border-fpl-green" : "border-white/20"
          }`}
        >
          <div className="flex items-center gap-2.5">
            <span
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-base ${
                chip.recommend ? "bg-fpl-green/15" : "bg-white/10"
              }`}
              aria-hidden="true"
            >
              {CHIP_ICON[chip.chip] ?? "🃏"}
            </span>
            <span className="font-heading text-sm font-bold text-fpl-white">{chip.chip}</span>
          </div>
          {/* Verbatim from the backend verdict — do NOT re-derive a reason
              here (a hardcoded "better fixtures coming" once contradicted the
              Best Gameweek panel below). */}
          <p className={`mt-2 text-sm font-medium ${chip.recommend ? "text-fpl-green" : "text-white/50"}`}>
            {chip.headline || (chip.recommend ? "Worth playing this week" : "Hold for now")}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-white/60">{chip.note}</p>
        </div>
      ))}

      {shown.length > 0 && (
        <div className="rounded-2xl bg-white/5 p-3 shadow-sm">
          <h3 className="font-heading text-xs font-bold uppercase tracking-wide text-white/70">
            Best Gameweek to Play
          </h3>
          <ul className="mt-2 flex flex-col divide-y divide-white/5">
            {shown.map((t, i) => (
              <li
                key={`${t.chip}-${t.gameweek}-${i}`}
                className="flex items-center justify-between py-1.5 text-xs first:pt-0 last:pb-0"
              >
                <span className="text-white/80">
                  GW{t.gameweek} · {t.chip}
                  {!t.worth_playing && (
                    <span className="ml-1.5 text-white/40">(below play bar)</span>
                  )}
                </span>
                <span className={`font-bold ${t.worth_playing ? "text-fpl-cyan" : "text-white/40"}`}>
                  +{t.predicted_gain.toFixed(1)}
                </span>
              </li>
            ))}
          </ul>
          {topNotWorth && (
            <p className="mt-2 border-t border-white/5 pt-2 text-[11px] leading-snug text-white/45">
              This ranks upcoming weeks relative to each other — none clear the
              threshold to actually play yet, so it doesn't override the “hold”
              verdict above.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
