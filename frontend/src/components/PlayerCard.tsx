import { fdrColor } from "../styles/theme";
import type { SquadPlayer } from "../types/fpl";
import Jersey from "./Jersey";

interface PlayerCardProps {
  player: SquadPlayer;
  isCaptain?: boolean;
  isViceCaptain?: boolean;
  fitnessFlag?: string;
  size?: "normal" | "small";
}

export default function PlayerCard({
  player,
  isCaptain = false,
  isViceCaptain = false,
  fitnessFlag,
  size = "normal",
}: PlayerCardProps) {
  const shirtSize = size === "small" ? 44 : 52;
  const cardWidth = size === "small" ? "w-[54px]" : "w-[62px]";
  const difficulty = player.avg_difficulty_next4;
  const fixtureLabel = player.opponent ? `${player.opponent} (${player.was_home ? "H" : "A"})` : null;

  return (
    <div className={`flex ${cardWidth} flex-col items-center`}>
      <div className="relative mb-1">
        <Jersey
          teamShortName={player.team}
          size={shirtSize}
          isGoalkeeper={player.position === "GKP"}
        />

        {isCaptain && (
          <span className="absolute -left-1.5 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-fpl-green text-[10px] font-bold text-fpl-black shadow-md ring-2 ring-fpl-purple-dark">
            C
          </span>
        )}
        {isViceCaptain && !isCaptain && (
          <span className="absolute -left-1.5 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-fpl-purple-light text-[10px] font-bold text-white shadow-md ring-2 ring-fpl-purple-dark">
            V
          </span>
        )}
        {fitnessFlag && (
          <span
            title={fitnessFlag}
            className="absolute -right-1.5 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-fpl-pink text-[10px] font-bold text-white shadow-md ring-2 ring-fpl-purple-dark"
          >
            !
          </span>
        )}
        {difficulty != null && (
          <span
            title={`Avg fixture difficulty (next 4): ${difficulty.toFixed(1)}`}
            className="absolute -bottom-1.5 -right-1 flex h-[18px] w-[18px] items-center justify-center rounded-full text-[9px] font-bold text-white shadow-md ring-2 ring-fpl-purple-dark"
            style={{ backgroundColor: fdrColor(difficulty) }}
          >
            {Math.round(difficulty)}
          </span>
        )}
      </div>

      <div className="w-full truncate rounded-full bg-white px-1.5 py-0.5 text-center text-[10.5px] font-semibold text-fpl-black shadow-sm">
        {player.web_name}
      </div>

      {/* opponent + predicted points combined into one chip — cyan number
          keeps the "this is a prediction" signal from the old separate pill */}
      <div className="mt-1 w-full rounded-lg bg-fpl-purple-dark px-1.5 py-1 text-center shadow-sm">
        {fixtureLabel && (
          <div className="truncate text-[8.5px] font-medium leading-tight text-white/55">
            {fixtureLabel}
          </div>
        )}
        <div className="text-[11px] font-bold leading-tight text-fpl-cyan">
          {(player.predicted_points ?? 0).toFixed(1)}
        </div>
      </div>
    </div>
  );
}
