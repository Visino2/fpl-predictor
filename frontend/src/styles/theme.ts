/**
 * Single source of truth for the FPL brand palette (see PROMPT_3_DESIGN.md).
 * Tailwind's config imports these — components should never hardcode hex
 * values, only Tailwind classes like `bg-fpl-purple-dark`.
 */
export const colors = {
  fplPurpleDark: "#38003C",
  fplPurpleLight: "#963CFF",
  fplGreen: "#00FF85",
  fplCyan: "#04F5FF",
  fplPink: "#E90052",
  fplWhite: "#FFFFFF",
  fplBlack: "#0D0D0D",

  pitchGreenDark: "#0A6E3C",
  pitchGreenLight: "#128C4A",
  pitchLines: "#FFFFFF",

  // Bench panel: muted/desaturated vs. the vivid pitch green, to read as "not playing"
  benchSage: "#8FA88F",
} as const;

export const gradients = {
  // The most distinctive FPL visual signature — the "Fantasy" banner atop the pitch
  fantasyBanner: "linear-gradient(120deg, #04F5FF 0%, #963CFF 55%, #38003C 100%)",
  // "Hero" stat card gradients (stat summary row / chip recommendation cards)
  heroCyanBlue: "linear-gradient(135deg, #04F5FF 0%, #3C7EFF 100%)",
  heroGreenCyan: "linear-gradient(135deg, #00FF85 0%, #04F5FF 100%)",
} as const;

export const fontFamily = {
  heading: ["Poppins", "Inter", "sans-serif"],
  body: ["Inter", "sans-serif"],
} as const;

/**
 * FPL's own fixture-difficulty color scale (1 = easiest, 5 = hardest) —
 * the standard green-to-red convention every FPL player already reads
 * fixtures by, so this reuses it rather than inventing a new one.
 */
export const fdrColors: Record<number, string> = {
  1: "#00A650", // dark green — easiest
  2: "#00FF85", // light green
  3: "#963CFF", // neutral (kept in-palette rather than FPL's grey)
  4: "#E90052", // pink/red — hard
  5: "#7A0030", // dark red — hardest
};

export function fdrColor(difficulty: number | null | undefined): string {
  if (difficulty == null) return "#8A8A8A";
  const rounded = Math.min(5, Math.max(1, Math.round(difficulty)));
  return fdrColors[rounded];
}
