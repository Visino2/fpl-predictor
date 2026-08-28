import type { ReactNode } from "react";
import type {
  SeasonCheckAdvice,
  TripleCaptainAdvice,
  WildcardFreehitAdvice,
} from "../types/fpl";

interface StrategyDashboardProps {
  loading: boolean;
  error: string | null;
  wildcard: WildcardFreehitAdvice | null;
  tripleCaptain: TripleCaptainAdvice | null;
  seasonCheck: SeasonCheckAdvice | null;
}

// Verdicts that mean "act" get the pink alert treatment; "all clear" verdicts
// go green; everything in between (wait / too early) stays neutral.
const ACT = new Set(["play now", "underperforming predictions", "below pace"]);
const CLEAR = new Set(["hold", "on track"]);

function verdictClasses(verdict: string): string {
  if (ACT.has(verdict)) return "bg-fpl-pink/15 text-fpl-pink";
  if (CLEAR.has(verdict)) return "bg-fpl-green/15 text-fpl-green";
  return "bg-white/10 text-white/60";
}

function Card({
  title,
  verdict,
  children,
}: {
  title: string;
  verdict: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-2xl bg-white/5 p-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-heading text-sm font-bold text-white/90">{title}</h2>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 text-[9px] font-bold uppercase tracking-wide ${verdictClasses(
            verdict,
          )}`}
        >
          {verdict}
        </span>
      </div>
      {children}
    </div>
  );
}

function ReasonList({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="mt-2 flex flex-col gap-1.5">
      {items.map((r, i) => (
        <li key={i} className="flex gap-2 text-[12px] leading-snug text-white/55">
          <span aria-hidden="true" className="mt-[3px] text-white/25">
            •
          </span>
          <span>{r}</span>
        </li>
      ))}
    </ul>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white/5 px-2 py-1.5 text-center">
      <div className="font-heading text-sm font-bold text-fpl-cyan">{value}</div>
      <div className="mt-0.5 text-[9px] font-bold uppercase tracking-wide text-white/45">{label}</div>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return <div className="rounded-2xl bg-white/5 p-6 text-center text-sm text-white/60">{message}</div>;
}

function num(v: number | null | undefined, digits = 1): string {
  return v == null ? "—" : v.toFixed(digits);
}

export default function StrategyDashboard({
  loading,
  error,
  wildcard,
  tripleCaptain,
  seasonCheck,
}: StrategyDashboardProps) {
  if (loading) {
    return (
      <div className="flex flex-col gap-4 px-3 pt-3 md:px-6">
        <div className="h-40 animate-pulse rounded-2xl bg-white/10" />
        <div className="h-40 animate-pulse rounded-2xl bg-white/10" />
        <div className="h-40 animate-pulse rounded-2xl bg-white/10" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="px-3 pt-3 md:px-6">
        <EmptyState message={`Couldn't load strategy data: ${error}`} />
      </div>
    );
  }

  const s = seasonCheck?.season_to_date ?? {};

  return (
    <div className="flex flex-col gap-4 px-3 pb-8 pt-3 md:grid md:grid-cols-2 md:items-start md:gap-4 md:px-6">
      {/* 1. Wildcard / Free Hit */}
      {wildcard && (
        <Card title="Wildcard / Free Hit" verdict={wildcard.verdict}>
          <p className="mt-2 text-[13px] font-semibold leading-snug text-fpl-white">
            {wildcard.headline}
          </p>
          <ReasonList items={wildcard.reasons} />
          <p className="mt-3 border-t border-white/10 pt-2 text-[11.5px] leading-snug text-white/45">
            {wildcard.chip_guidance}
          </p>
        </Card>
      )}

      {/* 2. Triple Captain */}
      {tripleCaptain && (
        <Card title="Triple Captain" verdict={tripleCaptain.verdict}>
          {tripleCaptain.best_candidate ? (
            <div className="mt-2 flex items-baseline gap-2">
              <span className="font-heading text-lg font-bold text-fpl-white">
                {tripleCaptain.best_candidate}
              </span>
              {typeof tripleCaptain.profile?.predicted_points === "number" && (
                <span className="text-xs font-semibold text-fpl-cyan">
                  {(tripleCaptain.profile.predicted_points as number).toFixed(1)} pts proj.
                </span>
              )}
            </div>
          ) : (
            <p className="mt-2 text-[13px] font-semibold text-fpl-white">No viable candidate this week</p>
          )}
          <p className="mt-1 text-[12px] leading-snug text-white/70">{tripleCaptain.note}</p>
          <ReasonList items={tripleCaptain.reasoning} />
          {tripleCaptain.considered.length > 1 && (
            <p className="mt-3 border-t border-white/10 pt-2 text-[10.5px] leading-snug text-white/40">
              Also weighed:{" "}
              {tripleCaptain.considered
                .slice(1)
                .map((c) => `${c.web_name} (${c.predicted_points.toFixed(1)})`)
                .join(", ")}
            </p>
          )}
        </Card>
      )}

      {/* 3. Season accumulation check — spans both columns on desktop */}
      {seasonCheck && (
        <div className="md:col-span-2">
          <Card title="Season Pace Check" verdict={seasonCheck.verdict}>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="Pts / GW" value={num(s.avg_points_per_gw)} />
              <Stat label="Good-rank pace" value={num(s.good_rank_pace, 0)} />
              <Stat
                label="vs predictions"
                value={
                  s.delta_vs_predictions == null
                    ? "—"
                    : `${s.delta_vs_predictions >= 0 ? "+" : ""}${s.delta_vs_predictions.toFixed(1)}`
                }
              />
              <Stat
                label="Hits cost"
                value={
                  s.transfer_hits_cost == null
                    ? "—"
                    : s.transfer_hits_cost === 0
                      ? "0"
                      : `-${s.transfer_hits_cost}`
                }
              />
            </div>
            <ReasonList items={seasonCheck.signals} />
            <p className="mt-3 border-t border-white/10 pt-2 text-[12px] leading-snug text-white/60">
              {seasonCheck.diagnosis}
            </p>
          </Card>
        </div>
      )}
    </div>
  );
}
