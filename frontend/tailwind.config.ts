import type { Config } from "tailwindcss";
import { colors, fontFamily, gradients } from "./src/styles/theme";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "fpl-purple-dark": colors.fplPurpleDark,
        "fpl-purple-light": colors.fplPurpleLight,
        "fpl-green": colors.fplGreen,
        "fpl-cyan": colors.fplCyan,
        "fpl-pink": colors.fplPink,
        "fpl-white": colors.fplWhite,
        "fpl-black": colors.fplBlack,
        "pitch-green-dark": colors.pitchGreenDark,
        "pitch-green-light": colors.pitchGreenLight,
        "pitch-lines": colors.pitchLines,
        "bench-sage": colors.benchSage,
      },
      fontFamily: {
        heading: fontFamily.heading,
        body: fontFamily.body,
      },
      backgroundImage: {
        "fantasy-banner": gradients.fantasyBanner,
        "hero-cyan-blue": gradients.heroCyanBlue,
        "hero-green-cyan": gradients.heroGreenCyan,
      },
    },
  },
  plugins: [],
} satisfies Config;
