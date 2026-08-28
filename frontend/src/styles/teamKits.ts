/**
 * Team kit rendering data.
 *
 * Primary path: the official FPL shirt renders, downloaded once into
 * `public/kits/` (they don't change mid-season). Keyed off each club's FPL
 * "team code" (bootstrap.json `teams[].code`), which is what FPL's own shirt
 * image filenames use — distinct from the 1–20 `team.id`.
 *
 * Fallback path: an approximate flat colour kit for any club we don't have a
 * code/image for, so a squad still renders if the map is stale.
 */

// short_name -> FPL team code (used in shirt_{code}.png / shirt_{code}_1.png)
export const TEAM_CODE: Record<string, number> = {
  ARS: 3,
  AVL: 7,
  BOU: 91,
  BRE: 94,
  BHA: 36,
  CHE: 8,
  COV: 9,
  CRY: 31,
  EVE: 11,
  FUL: 54,
  HUL: 88,
  IPS: 40,
  LEE: 2,
  LIV: 14,
  MCI: 43,
  MUN: 1,
  NEW: 4,
  NFO: 17,
  TOT: 6,
  SUN: 56,
};

/**
 * Path to a cached FPL shirt render, or `null` if we don't have a code for
 * this club (caller should fall back to the drawn kit). `_1` is FPL's
 * goalkeeper-shirt suffix.
 */
export function kitImagePath(
  teamShortName: string | null | undefined,
  isGoalkeeper: boolean,
): string | null {
  if (!teamShortName) return null;
  const code = TEAM_CODE[teamShortName];
  if (code == null) return null;
  return `/kits/shirt_${code}${isGoalkeeper ? "_1" : ""}.png`;
}

// ---- Fallback flat kit (only used when a code/image is missing) -------------

export type KitPattern = "solid" | "stripes" | "hoops";

export interface Kit {
  primary: string;
  secondary: string;
  pattern: KitPattern;
}

export const TEAM_KITS: Record<string, Kit> = {
  ARS: { primary: "#DA020E", secondary: "#FFFFFF", pattern: "solid" },
  AVL: { primary: "#670E36", secondary: "#94BEE5", pattern: "solid" },
  BOU: { primary: "#DA291C", secondary: "#000000", pattern: "stripes" },
  BRE: { primary: "#E30613", secondary: "#FFFFFF", pattern: "stripes" },
  BHA: { primary: "#0057B8", secondary: "#FFFFFF", pattern: "stripes" },
  CHE: { primary: "#034694", secondary: "#0A2240", pattern: "solid" },
  COV: { primary: "#78D0F2", secondary: "#1B1B1B", pattern: "solid" },
  CRY: { primary: "#C4122E", secondary: "#1B458F", pattern: "stripes" },
  EVE: { primary: "#003399", secondary: "#FFFFFF", pattern: "solid" },
  FUL: { primary: "#FFFFFF", secondary: "#000000", pattern: "solid" },
  HUL: { primary: "#F5A623", secondary: "#000000", pattern: "stripes" },
  IPS: { primary: "#0044A9", secondary: "#FFFFFF", pattern: "solid" },
  LEE: { primary: "#FFFFFF", secondary: "#FFCD00", pattern: "solid" },
  LIV: { primary: "#C8102E", secondary: "#00285E", pattern: "solid" },
  MCI: { primary: "#6CABDD", secondary: "#FFFFFF", pattern: "solid" },
  MUN: { primary: "#DA291C", secondary: "#000000", pattern: "solid" },
  NEW: { primary: "#000000", secondary: "#FFFFFF", pattern: "stripes" },
  NFO: { primary: "#DD0000", secondary: "#FFFFFF", pattern: "solid" },
  TOT: { primary: "#FFFFFF", secondary: "#132257", pattern: "solid" },
  SUN: { primary: "#EB172B", secondary: "#FFFFFF", pattern: "stripes" },
};

export const DEFAULT_KIT: Kit = { primary: "#8A8A8A", secondary: "#FFFFFF", pattern: "solid" };

export function getKit(teamShortName: string | null | undefined): Kit {
  if (!teamShortName) return DEFAULT_KIT;
  return TEAM_KITS[teamShortName] ?? DEFAULT_KIT;
}
