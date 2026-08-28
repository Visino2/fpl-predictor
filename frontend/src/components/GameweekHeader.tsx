import type { GwStatus } from "../types/fpl";

interface GameweekHeaderProps {
  gw: number;
  requestedGw: number | null;
  gwStatus: GwStatus | null;
  teamName: string | null;
  totalPredictedPoints: number;
  loading?: boolean;
  onRefresh: () => void;
  onChipsClick: () => void;
}

export default function GameweekHeader({
  gw,
  requestedGw,
  gwStatus,
  teamName,
  totalPredictedPoints,
  loading,
  onRefresh,
  onChipsClick,
}: GameweekHeaderProps) {
  const isLocked = gwStatus === "locked";

  return (
    <header className="bg-fpl-purple-dark px-4 pb-5 pt-4 md:px-6">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          {teamName && <p className="truncate text-[11px] font-medium text-white/50">{teamName}</p>}
          <div className="flex items-center gap-1.5">
            <h1 className="truncate font-heading text-lg font-bold text-fpl-white">
              Gameweek {gw || "…"}
            </h1>
            {isLocked && (
              <span
                title={
                  requestedGw
                    ? `GW${requestedGw}'s picks aren't published yet — showing your last-locked squad instead.`
                    : undefined
                }
                className="shrink-0 rounded-full bg-fpl-pink/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-fpl-pink"
              >
                Locked
              </span>
            )}
          </div>
          {isLocked && requestedGw && (
            <p className="truncate text-[11px] text-white/50">
              GW{requestedGw} picks not published yet
            </p>
          )}
        </div>
        <button
          aria-label="Refresh"
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/10 text-fpl-white transition active:scale-95 disabled:opacity-50"
        >
          <span className={loading ? "inline-block animate-spin" : ""}>↻</span>
        </button>
      </div>

      <div className="mt-4 grid grid-cols-3 items-center gap-2">
        <div className="text-center">
          <div className="font-heading text-lg font-bold text-fpl-white">GW{gw || "-"}</div>
          <div className="text-xs text-white/60">Gameweek</div>
        </div>

        <div className="bg-hero-cyan-blue rounded-2xl px-3 py-2 text-center shadow-sm">
          <div className="font-heading text-xl font-extrabold text-fpl-black">
            {loading ? "…" : totalPredictedPoints.toFixed(1)}
          </div>
          <div className="text-[11px] font-medium text-fpl-black/80">Predicted Total</div>
        </div>

        <button
          className="text-center transition active:scale-95"
          type="button"
          onClick={onChipsClick}
        >
          <div className="font-heading text-lg font-bold text-fpl-white">Chips</div>
          <div className="text-xs text-white/60">View all ›</div>
        </button>
      </div>
    </header>
  );
}
