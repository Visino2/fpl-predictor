import { useState } from "react";
import { getKit, kitImagePath } from "../styles/teamKits";

interface JerseyProps {
  teamShortName?: string | null;
  size: number; // px width; height follows the shirt's natural ratio
  isGoalkeeper?: boolean;
}

// Fallback silhouette — only rendered when we have no cached FPL kit render for
// the club (unknown short_name, or the PNG failed to load). Raglan-sleeve shirt
// with a V-neck, shaded like fabric rather than a flat rectangle.
const SHIRT_PATH =
  "M32,14 Q41,22 50,28 Q59,22 68,14 L86,26 L97,35 L87,45 L80,40 L80,94 Q50,100 20,94 L20,40 L13,45 L3,35 L14,26 Z";
const COLLAR_PATH = "M32,14 Q41,22 50,28 Q59,22 68,14";

function FallbackJersey({
  teamShortName,
  size,
  isGoalkeeper,
}: Required<Pick<JerseyProps, "teamShortName" | "size" | "isGoalkeeper">>) {
  const kit = getKit(teamShortName);
  // GK gets a contrasting striped shirt so it reads as distinct from the
  // outfield solids, mirroring the real app.
  const primary = isGoalkeeper ? "#1FE87B" : kit.primary;
  const secondary = isGoalkeeper ? "#0A2E1C" : kit.secondary;
  const pattern = isGoalkeeper ? "stripes" : kit.pattern;
  const uid = `${teamShortName ?? "default"}${isGoalkeeper ? "-gk" : ""}`;
  const clipId = `jersey-clip-${uid}`;
  const shadeId = `jersey-shade-${uid}`;
  const shadowId = `jersey-shadow-${uid}`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      style={{ overflow: "visible", display: "block" }}
      aria-hidden="true"
    >
      <defs>
        <clipPath id={clipId}>
          <path d={SHIRT_PATH} />
        </clipPath>
        <linearGradient id={shadeId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.4" />
          <stop offset="40%" stopColor="#ffffff" stopOpacity="0" />
          <stop offset="100%" stopColor="#000000" stopOpacity="0.15" />
        </linearGradient>
        <filter id={shadowId} x="-40%" y="-40%" width="180%" height="180%">
          <feDropShadow dx="0" dy="2.5" stdDeviation="2.5" floodColor="#000000" floodOpacity="0.35" />
        </filter>
      </defs>

      <g filter={`url(#${shadowId})`}>
        <g clipPath={`url(#${clipId})`}>
          <rect x="0" y="0" width="100" height="100" fill={primary} />
          {pattern === "stripes" &&
            [0, 25, 50, 75].map((x) => (
              <rect key={x} x={x} y="0" width="12.5" height="100" fill={secondary} />
            ))}
          {pattern === "hoops" &&
            [0, 25, 50, 75].map((y) => (
              <rect key={y} x="0" y={y} width="100" height="12.5" fill={secondary} />
            ))}
          <rect x="0" y="0" width="100" height="100" fill={`url(#${shadeId})`} />
        </g>

        <path d={COLLAR_PATH} fill="none" stroke="#000000" strokeOpacity="0.25" strokeWidth="3.5" strokeLinecap="round" />
        <path d={COLLAR_PATH} fill="none" stroke={secondary} strokeOpacity="0.9" strokeWidth="2" strokeLinecap="round" />
        <path d={SHIRT_PATH} fill="none" stroke="#00000030" strokeWidth="1.5" />
      </g>
    </svg>
  );
}

export default function Jersey({ teamShortName, size, isGoalkeeper = false }: JerseyProps) {
  const [imgFailed, setImgFailed] = useState(false);
  const src = kitImagePath(teamShortName, isGoalkeeper);

  if (!src || imgFailed) {
    return (
      <FallbackJersey
        teamShortName={teamShortName ?? "default"}
        size={size}
        isGoalkeeper={isGoalkeeper}
      />
    );
  }

  return (
    <img
      src={src}
      alt=""
      aria-hidden="true"
      width={size}
      draggable={false}
      onError={() => setImgFailed(true)}
      style={{
        width: size,
        height: "auto",
        display: "block",
        filter: "drop-shadow(0 2px 2.5px rgba(0,0,0,0.35))",
      }}
    />
  );
}
