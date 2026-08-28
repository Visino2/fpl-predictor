import type { TransferSuggestion } from "../types/fpl";

interface TransferSuggestionsProps {
  suggestions: TransferSuggestion[];
}

function CostBadge({ transferCost }: { transferCost: string }) {
  const isFree = transferCost === "free";
  return (
    <span
      className={`shrink-0 rounded-full px-2 py-0.5 text-[9px] font-bold uppercase ${
        isFree ? "bg-fpl-green/15 text-fpl-green" : "bg-fpl-pink/15 text-fpl-pink"
      }`}
    >
      {isFree ? "Free" : transferCost}
    </span>
  );
}

export default function TransferSuggestions({ suggestions }: TransferSuggestionsProps) {
  if (suggestions.length === 0) return null;

  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-heading text-sm font-bold text-white/90">Transfer Suggestions</h2>
      {suggestions.map((s) => (
        <div
          key={`${s.out_player}-${s.in_player}`}
          className="rounded-2xl bg-white/5 p-3 shadow-sm transition-colors hover:bg-white/[0.07]"
        >
          <div className="flex items-center gap-2 text-sm">
            <span className="min-w-0 flex-1 truncate text-white/50 line-through">{s.out_player}</span>
            <span
              aria-hidden="true"
              className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-fpl-green/15 text-[10px] text-fpl-green"
            >
              →
            </span>
            <span className="min-w-0 flex-1 truncate text-right font-semibold text-fpl-white">
              {s.in_player}
            </span>
            <CostBadge transferCost={s.transfer_cost} />
          </div>
          <div className="mt-1.5 flex items-center justify-between text-xs">
            <span className="flex items-baseline gap-1.5">
              <span className="text-white/45">
                {s.out_predicted_points.toFixed(1)}
                <span className="mx-1 text-white/30">→</span>
                <span className="font-semibold text-white/70">{s.in_predicted_points.toFixed(1)}</span>
              </span>
              <span className="font-bold text-fpl-cyan">+{s.predicted_gain.toFixed(1)} pts</span>
            </span>
            <span className="text-white/50">
              {s.cost_change >= 0 ? "+" : ""}
              {s.cost_change.toFixed(1)}m
            </span>
          </div>

          {s.reasons.length > 0 && (
            <p className="mt-1.5 text-[10.5px] leading-snug text-white/40">
              {s.in_player}: {s.reasons.join(" · ")}
            </p>
          )}
        </div>
      ))}
    </section>
  );
}
