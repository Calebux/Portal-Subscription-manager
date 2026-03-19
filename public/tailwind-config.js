// Tailwind CDN config — loaded as a local file to comply with MV3 CSP
tailwind.config = {
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "background": "#10141a", "surface": "#10141a", "surface-dim": "#10141a",
        "surface-container": "#1c2026", "surface-container-low": "#181c22",
        "surface-container-lowest": "#0a0e14", "surface-container-high": "#262a31",
        "surface-container-highest": "#31353c", "surface-bright": "#353940",
        "surface-variant": "#31353c", "surface-tint": "#22d3ee",
        "on-surface": "#dfe2eb", "on-surface-variant": "#c7c4d7",
        "on-background": "#dfe2eb", "outline": "#908fa0", "outline-variant": "#464554",
        "primary": "#22d3ee", "primary-fixed": "#97f0ff", "primary-container": "#22d3ee",
        "on-primary": "#003638", "on-primary-container": "#002022",
        "secondary": "#5de6ff", "secondary-container": "#00cbe6",
        "on-secondary": "#00363e", "secondary-fixed-dim": "#2fd9f4",
        "tertiary": "#4edea3", "tertiary-fixed": "#6ffbbe",
        "on-tertiary": "#003824", "tertiary-container": "#00885d",
        "error": "#ffb4ab", "error-container": "#93000a",
        "on-error": "#690005", "on-error-container": "#ffdad6",
        "inverse-surface": "#dfe2eb", "inverse-on-surface": "#2d3137",
        "inverse-primary": "#00696e"
      },
      fontFamily: {
        "headline": ["Inter", "sans-serif"], "body": ["Inter", "sans-serif"],
        "label": ["Inter", "sans-serif"], "mono": ["JetBrains Mono", "monospace"]
      },
      borderRadius: {
        "DEFAULT": "0.125rem", "lg": "0.25rem", "xl": "0.5rem",
        "2xl": "0.75rem", "3xl": "1rem", "full": "9999px"
      }
    }
  }
};
