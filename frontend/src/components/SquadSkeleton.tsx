// Mirrors Pitch + BenchRow's real layout so loading doesn't cause a jump —
// a plausible 1-4-4-2 shape stands in until the real squad/formation loads.
const ROW_COUNTS = [1, 4, 4, 2];

function GhostCard({ small = false }: { small?: boolean }) {
  const size = small ? "h-8 w-8" : "h-10 w-10";
  const width = small ? "w-[54px]" : "w-[62px]";
  return (
    <div className={`flex ${width} flex-col items-center`}>
      <div className={`${size} animate-pulse rounded-md bg-white/25`} />
      <div className="mt-1.5 h-3.5 w-full animate-pulse rounded-full bg-white/25" />
      <div className="mt-1 h-3.5 w-full animate-pulse rounded-full bg-white/15" />
    </div>
  );
}

export default function SquadSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-hidden rounded-2xl shadow-sm">
        <div className="bg-fantasy-banner flex items-center justify-between px-4 py-1.5 font-heading text-xs font-extrabold tracking-widest text-white/70">
          <span>FANTASY</span>
          <span>FANTASY</span>
        </div>
        <div
          className="flex flex-col justify-around gap-4 px-2 py-5"
          style={{
            backgroundColor: "#0A6E3C",
            backgroundImage:
              "repeating-linear-gradient(135deg, #128C4A 0, #128C4A 36px, #0A6E3C 36px, #0A6E3C 72px)",
          }}
        >
          {ROW_COUNTS.map((count, row) => (
            <div key={row} className="flex justify-center gap-2">
              {Array.from({ length: count }).map((_, i) => (
                <GhostCard key={i} />
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-2xl bg-bench-sage/25 px-3 py-3">
        <div className="mb-2 h-2.5 w-12 animate-pulse rounded-full bg-white/25" />
        <div className="flex justify-between gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <GhostCard key={i} small />
          ))}
        </div>
      </div>
    </div>
  );
}
