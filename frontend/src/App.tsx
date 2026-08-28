import { useRef, useState } from "react";
import AccuracyDashboard from "./components/AccuracyDashboard";
import BenchRow from "./components/BenchRow";
import ChipPanel from "./components/ChipPanel";
import GameweekHeader from "./components/GameweekHeader";
import LineupCheck from "./components/LineupCheck";
import Pitch from "./components/Pitch";
import SquadSkeleton from "./components/SquadSkeleton";
import StrategyDashboard from "./components/StrategyDashboard";
import TabSwitcher from "./components/TabSwitcher";
import TopPicks from "./components/TopPicks";
import TransferSuggestions from "./components/TransferSuggestions";
import { useAccuracy } from "./hooks/useAccuracy";
import { useSquad } from "./hooks/useSquad";
import { useStrategy } from "./hooks/useStrategy";

type Tab = "team" | "strategy" | "accuracy";

// Short "what is this tab for" line under the switcher — keeps the weekly
// tactical view and the season-level view from being confused for each other.
const TAB_SUBTITLE: Record<Tab, string> = {
  team: "Weekly tactical view — this week's XI, chip timing, and obvious free transfers.",
  strategy: "Season-level decisions — structural moves, not weekly tinkering.",
  accuracy: "How close the model's point predictions have tracked real results.",
};

export default function App() {
  const [tab, setTab] = useState<Tab>("team");

  const {
    loading,
    error,
    gw,
    requestedGw,
    gwStatus,
    teamName,
    squad,
    squadPredictedTotal,
    predictions,
    chips,
    chipTiming,
    transfers,
    lineup,
    refresh,
  } = useSquad();
  const accuracy = useAccuracy();
  const strategy = useStrategy();
  const chipsRef = useRef<HTMLDivElement>(null);

  if (error) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-fpl-purple-dark p-6 text-center">
        <p className="font-heading text-lg font-bold text-fpl-white">Couldn't load your squad</p>
        <p className="text-sm text-white/60">{error}</p>
        <button
          type="button"
          onClick={refresh}
          className="rounded-full bg-fpl-green px-4 py-2 text-sm font-bold text-fpl-black"
        >
          Retry
        </button>
      </div>
    );
  }

  const starters = squad.filter((p) => p.is_starter);
  const bench = squad.filter((p) => !p.is_starter);

  return (
    <div className="mx-auto min-h-screen max-w-[430px] overflow-x-hidden bg-fpl-purple-dark pb-8 md:max-w-4xl">
      <GameweekHeader
        gw={gw}
        requestedGw={requestedGw}
        gwStatus={gwStatus}
        teamName={teamName}
        totalPredictedPoints={squadPredictedTotal}
        loading={loading}
        onRefresh={refresh}
        onChipsClick={() => {
          setTab("team");
          requestAnimationFrame(() => chipsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
        }}
      />

      <div className="px-3 pt-3 md:px-6">
        {/* Tablet+: keep the switcher from stretching edge-to-edge across a wide header */}
        <div className="md:max-w-md">
          <TabSwitcher
            tabs={[
              { id: "team", label: "My Team" },
              { id: "strategy", label: "Strategy" },
              { id: "accuracy", label: "Accuracy" },
            ]}
            active={tab}
            onChange={setTab}
          />
          <p className="mt-1.5 px-1 text-[11px] leading-snug text-white/45">{TAB_SUBTITLE[tab]}</p>
        </div>
      </div>

      {tab === "team" ? (
        <main className="flex flex-col gap-4 px-3 pt-3 md:grid md:grid-cols-[1.4fr_1fr] md:items-start md:gap-5 md:px-6">
          <div className="flex flex-col gap-4">
            {squad.length > 0 ? (
              <>
                <Pitch starters={starters} />
                <BenchRow bench={bench} />
              </>
            ) : (
              <SquadSkeleton />
            )}
          </div>

          <div className="flex flex-col gap-4">
            <div ref={chipsRef}>
              <ChipPanel chips={chips} timing={chipTiming} />
            </div>
            <LineupCheck lineup={lineup} />
            <TransferSuggestions suggestions={transfers} />
            <TopPicks
              predictions={predictions}
              squadPlayerIds={squad.map((p) => p.player_id).filter((id): id is number => id != null)}
            />
          </div>
        </main>
      ) : tab === "strategy" ? (
        <StrategyDashboard
          loading={strategy.loading}
          error={strategy.error}
          wildcard={strategy.wildcard}
          tripleCaptain={strategy.tripleCaptain}
          seasonCheck={strategy.seasonCheck}
        />
      ) : (
        <AccuracyDashboard
          loading={accuracy.loading}
          error={accuracy.error}
          report={accuracy.report}
          chipHistory={accuracy.chipHistory}
        />
      )}
    </div>
  );
}
