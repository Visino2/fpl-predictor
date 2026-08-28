import type { PlayerPrediction } from "../types/fpl";

interface TopPicksProps {
  predictions: PlayerPrediction[];
  squadPlayerIds: number[];
  limit?: number;
}

export default function TopPicks({ predictions, squadPlayerIds, limit = 8 }: TopPicksProps) {
  const inSquad = new Set(squadPlayerIds);

  // "Safer" picks: no injury/doubt flag, ranked by predicted points — the
  // strongest signal combination this model has. Never a guarantee (see
  // each position's real MAE on the Accuracy tab) — this is a ranking, not
  // a promise.
  const picks = predictions
    .filter((p) => !p.fitness_flag)
    .sort((a, b) => b.predicted_points - a.predicted_points)
    .slice(0, limit);

  if (picks.length === 0) return null;

  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <h2 className="font-heading text-sm font-bold text-white/90">Top Picks This Gameweek</h2>
        <span className="text-[10px] text-white/40">no injury/doubt flag</span>
      </div>

      <div className="flex flex-col gap-2">
        {picks.map((p, i) => (
          <div
            key={p.player_id}
            className="flex items-center gap-2.5 rounded-2xl bg-white/5 p-2.5 shadow-sm transition-colors hover:bg-white/[0.07]"
          >
            <span
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                i === 0 ? "bg-fpl-green text-fpl-black" : "bg-white/10 text-white/60"
              }`}
              title={i === 0 ? "Best captain option" : undefined}
            >
              {i === 0 ? "★" : i + 1}
            </span>

            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="truncate text-sm font-semibold text-fpl-white">{p.web_name}</span>
                <span className="shrink-0 text-[9px] font-bold uppercase text-white/40">{p.position}</span>
                {inSquad.has(p.player_id) && (
                  <span className="shrink-0 rounded-full bg-fpl-purple-light/20 px-1.5 py-0.5 text-[8px] font-bold uppercase text-fpl-purple-light">
                    In squad
                  </span>
                )}
              </div>
              <div className="text-[10px] text-white/50">
                £{p.now_cost.toFixed(1)}m · vs {p.opponent} ({p.was_home ? "H" : "A"})
              </div>
            </div>

            <span className="shrink-0 text-base font-bold text-fpl-cyan">
              {p.predicted_points.toFixed(1)}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
