import type { LineupRecommendation } from "../types/fpl";

interface LineupCheckProps {
  lineup: LineupRecommendation | null;
}

// Mirrors TransferSuggestions' swap-card style: strikethrough out-player,
// arrow, bold in-player, points delta, then grey reason clauses.
function SwapCard({ swap }: { swap: LineupRecommendation["swaps"][number] }) {
  return (
    <div className="rounded-2xl bg-white/5 p-3 shadow-sm transition-colors hover:bg-white/[0.07]">
      <div className="flex items-center gap-2 text-sm">
        <span className="min-w-0 flex-1 truncate text-white/50 line-through">
          {swap.out} <span className="text-[10px] no-underline">({swap.out_position})</span>
        </span>
        <span
          aria-hidden="true"
          className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-fpl-green/15 text-[10px] text-fpl-green"
        >
          →
        </span>
        <span className="min-w-0 flex-1 truncate text-right font-semibold text-fpl-white">
          {swap.in} <span className="text-[10px] font-normal text-white/50">({swap.in_position})</span>
        </span>
      </div>
      <div className="mt-1.5 flex items-baseline gap-1.5 text-xs">
        <span className="text-white/45">
          {swap.out_predicted_points.toFixed(1)}
          <span className="mx-1 text-white/30">→</span>
          <span className="font-semibold text-white/70">{swap.in_predicted_points.toFixed(1)}</span>
        </span>
        <span className="font-bold text-fpl-cyan">+{swap.gain.toFixed(1)} pts</span>
      </div>
      {swap.reasons.length > 0 && (
        <p className="mt-1.5 text-[10.5px] leading-snug text-white/40">
          {swap.in}: {swap.reasons.join(" · ")}
        </p>
      )}
    </div>
  );
}

export default function LineupCheck({ lineup }: LineupCheckProps) {
  if (!lineup) return null;

  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-heading text-sm font-bold text-white/90">Lineup Check</h2>

      {lineup.is_optimal ? (
        <div className="rounded-2xl border-l-4 border-fpl-green bg-white/5 p-3 shadow-sm">
          <p className="text-sm font-medium text-fpl-green">
            Your lineup is already optimal for this gameweek
          </p>
          <p className="mt-1 text-xs text-white/55">
            {lineup.actual.formation} · {lineup.actual.predicted_points.toFixed(1)} projected pts —
            no bench player would out-score a starter.
          </p>
        </div>
      ) : (
        <>
          <div className="rounded-2xl bg-white/5 p-3 shadow-sm">
            <div className="flex items-center justify-between text-xs">
              <div>
                <div className="text-white/45">Your XI</div>
                <div className="font-semibold text-white/80">
                  {lineup.actual.formation} · {lineup.actual.predicted_points.toFixed(1)} pts
                </div>
              </div>
              <span aria-hidden="true" className="text-white/30">→</span>
              <div className="text-right">
                <div className="text-white/45">Optimizer</div>
                <div className="font-semibold text-white/80">
                  {lineup.suggested.formation} · {lineup.suggested.predicted_points.toFixed(1)} pts
                </div>
              </div>
              <span className="ml-2 shrink-0 rounded-full bg-fpl-cyan/15 px-2 py-0.5 text-[11px] font-bold text-fpl-cyan">
                +{lineup.predicted_points_gain.toFixed(1)}
              </span>
            </div>
          </div>

          {lineup.swaps.map((s) => (
            <SwapCard key={`${s.out}-${s.in}`} swap={s} />
          ))}

          <p className="px-1 text-[11px] leading-snug text-white/45">
            A suggestion to make yourself in the FPL app if you agree — not an automatic change.
          </p>
        </>
      )}
    </section>
  );
}
