import type { SquadPlayer } from "../types/fpl";
import PlayerCard from "./PlayerCard";

interface BenchRowProps {
  bench: SquadPlayer[];
}

export default function BenchRow({ bench }: BenchRowProps) {
  return (
    <div className="rounded-2xl bg-bench-sage/25 px-3 py-3">
      <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-white/70">Bench</div>
      <div className="flex justify-between gap-2">
        {bench.map((p) => (
          <div key={p.player_id ?? p.web_name} className="flex flex-col items-center">
            <span className="mb-1 text-[9px] font-bold uppercase tracking-wide text-white/50">
              {p.position}
            </span>
            <PlayerCard player={p} size="small" />
          </div>
        ))}
      </div>
    </div>
  );
}
