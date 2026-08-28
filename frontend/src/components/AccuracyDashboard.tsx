import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AccuracyReport, ChipLogEntry } from "../types/fpl";
import { colors } from "../styles/theme";

interface AccuracyDashboardProps {
  loading: boolean;
  error: string | null;
  report: AccuracyReport | null;
  chipHistory: ChipLogEntry[];
}

const POSITION_ORDER = ["GKP", "DEF", "MID", "FWD"];

const CHIP_LABEL: Record<string, string> = {
  bboost: "Bench Boost",
  "3xc": "Triple Captain",
  wildcard: "Wildcard",
  freehit: "Free Hit",
};

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-2xl bg-white/5 p-6 text-center text-sm text-white/60">{message}</div>
  );
}

export default function AccuracyDashboard({ loading, error, report, chipHistory }: AccuracyDashboardProps) {
  if (loading) {
    return (
      <div className="flex flex-col gap-4 px-3 pt-3 md:px-6">
        <div className="h-24 animate-pulse rounded-2xl bg-white/10" />
        <div className="h-48 animate-pulse rounded-2xl bg-white/10" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="px-3 pt-3 md:px-6">
        <EmptyState message={`Couldn't load accuracy data: ${error}`} />
      </div>
    );
  }

  const hasAnyData = report && report.sample_size > 0;
  const hasTrend = report && report.weeks.length >= 2;
  const latestWeek = report?.weeks[report.weeks.length - 1] ?? null;

  return (
    <div className="flex flex-col gap-4 px-3 pb-8 pt-3 md:px-6">
      {/* Hero stat row — same 3-column pattern as GameweekHeader's stat row */}
      <div className="grid grid-cols-3 items-center gap-2 md:max-w-md">
        <div className="text-center">
          <div className="font-heading text-lg font-bold text-fpl-white">
            {report?.gameweeks_covered ?? 0}
          </div>
          <div className="text-xs text-white/60">GWs Tracked</div>
        </div>

        <div className="bg-hero-green-cyan rounded-2xl px-3 py-2 text-center shadow-sm">
          <div className="font-heading text-xl font-extrabold text-fpl-black">
            {report?.overall_mae != null ? report.overall_mae.toFixed(2) : "—"}
          </div>
          <div className="text-[11px] font-medium text-fpl-black/80">Overall MAE</div>
        </div>

        <div className="text-center">
          <div className="font-heading text-lg font-bold text-fpl-white">
            {latestWeek?.actual_total != null ? latestWeek.actual_total.toFixed(0) : "—"}
          </div>
          <div className="text-xs text-white/60">
            {latestWeek ? `GW${latestWeek.gw} Actual` : "Latest GW"}
          </div>
        </div>
      </div>

      {!hasAnyData ? (
        <EmptyState message="Come back after a few gameweeks — need more data to show trends." />
      ) : (
        <div className="md:grid md:grid-cols-2 md:items-start md:gap-4">
          {/* Week-by-week predicted vs actual */}
          <div className="rounded-2xl bg-white/5 p-3 shadow-sm">
            <h2 className="font-heading text-sm font-bold text-white/90">Predicted vs Actual</h2>
            {hasTrend ? (
              <div className="mt-2 h-48 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={report!.weeks} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
                    <XAxis
                      dataKey="gw"
                      tickFormatter={(gw) => `GW${gw}`}
                      tick={{ fill: "rgba(255,255,255,0.6)", fontSize: 11 }}
                      axisLine={{ stroke: "rgba(255,255,255,0.15)" }}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fill: "rgba(255,255,255,0.6)", fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                      width={32}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: colors.fplPurpleDark,
                        border: "1px solid rgba(255,255,255,0.15)",
                        borderRadius: 12,
                        fontSize: 12,
                      }}
                      labelFormatter={(gw) => `Gameweek ${gw}`}
                      labelStyle={{ color: colors.fplWhite }}
                    />
                    <Legend wrapperStyle={{ fontSize: 11, color: "rgba(255,255,255,0.7)" }} />
                    <Line
                      type="monotone"
                      dataKey="predicted_total"
                      name="Predicted"
                      stroke={colors.fplCyan}
                      strokeWidth={2}
                      dot={{ r: 3, fill: colors.fplCyan }}
                    />
                    <Line
                      type="monotone"
                      dataKey="actual_total"
                      name="Actual"
                      stroke={colors.fplGreen}
                      strokeWidth={2}
                      dot={{ r: 3, fill: colors.fplGreen }}
                      connectNulls
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="mt-2">
                <EmptyState message="Come back after a few gameweeks — need more data to show trends." />
              </div>
            )}
          </div>

          {/* Per-position MAE */}
          <div className="mt-4 md:mt-0">
            <h2 className="mb-2 font-heading text-sm font-bold text-white/90">MAE by Position</h2>
            <div className="grid grid-cols-4 gap-2">
              {POSITION_ORDER.map((pos) => (
                <div key={pos} className="rounded-2xl bg-white/5 p-2.5 text-center shadow-sm">
                  <div className="font-heading text-base font-bold text-fpl-cyan">
                    {report!.mae_by_position[pos] != null ? report!.mae_by_position[pos].toFixed(2) : "—"}
                  </div>
                  <div className="mt-0.5 text-[10px] font-bold uppercase tracking-wide text-white/50">
                    {pos}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Chip history */}
      <div>
        <h2 className="mb-2 font-heading text-sm font-bold text-white/90">Chip History</h2>
        {chipHistory.length === 0 ? (
          <EmptyState message="No chip advice logged yet." />
        ) : (
          <div className="flex flex-col gap-2 md:grid md:grid-cols-2 md:gap-2">
            {chipHistory.map((c) => (
              <div key={`${c.gw}-${c.chip_name}`} className="rounded-2xl bg-white/5 p-3 shadow-sm">
                <div className="flex items-center justify-between">
                  <span className="font-heading text-sm font-bold text-fpl-white">
                    GW{c.gw} · {CHIP_LABEL[c.chip_name] ?? c.chip_name}
                  </span>
                  <div className="flex gap-1">
                    {c.was_recommended != null && (
                      <span
                        className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase ${
                          c.was_recommended ? "bg-fpl-green/15 text-fpl-green" : "bg-white/10 text-white/50"
                        }`}
                      >
                        {c.was_recommended ? "Recommended" : "Not recommended"}
                      </span>
                    )}
                    {c.was_played && (
                      <span className="rounded-full bg-fpl-purple-light/20 px-2 py-0.5 text-[9px] font-bold uppercase text-fpl-purple-light">
                        Played
                      </span>
                    )}
                  </div>
                </div>
                <div className="mt-1.5 flex items-center justify-between text-xs">
                  <span className="text-white/50">
                    Predicted: {c.predicted_gain != null ? c.predicted_gain.toFixed(1) : "—"}
                  </span>
                  <span className="font-bold text-fpl-cyan">
                    Actual: {c.actual_gain != null ? c.actual_gain.toFixed(1) : "—"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
