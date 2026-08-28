import type { Position, SquadPlayer } from "../types/fpl";
import PlayerCard from "./PlayerCard";

interface PitchProps {
  starters: SquadPlayer[];
}

const ROWS: Position[] = ["GKP", "DEF", "MID", "FWD"];

export default function Pitch({ starters }: PitchProps) {
  return (
    <div className="overflow-hidden rounded-2xl shadow-sm">
      {/* the most distinctive FPL visual signature */}
      <div className="bg-fantasy-banner flex items-center justify-between px-4 py-1.5 font-heading text-xs font-extrabold tracking-widest text-white">
        <span>FANTASY</span>
        <span>FANTASY</span>
      </div>

      <div
        className="relative flex flex-col justify-around gap-4 px-2 py-5"
        style={{
          backgroundColor: "#0A6E3C",
          backgroundImage:
            "repeating-linear-gradient(135deg, #128C4A 0, #128C4A 36px, #0A6E3C 36px, #0A6E3C 72px)",
        }}
      >
        {/* pitch markings, reduced opacity */}
        <div className="pointer-events-none absolute inset-3 rounded-lg border-2 border-white/25" />
        <div className="pointer-events-none absolute left-1/2 top-1/2 h-16 w-16 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white/25" />

        {ROWS.map((position) => {
          const players = starters.filter((p) => p.position === position);
          if (players.length === 0) return null;
          return (
            <div key={position} className="relative z-10 flex justify-center gap-2">
              {players.map((p) => (
                <PlayerCard
                  key={p.player_id ?? p.web_name}
                  player={p}
                  isCaptain={p.is_captain}
                  isViceCaptain={p.is_vice_captain ?? false}
                />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
