/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: ["./web/templates/**/*.html"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["IBM Plex Sans", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      colors: {
        ak: {
          red: "#C93528",
          "red-d": "#E03E38",
          bg: "#EDE8DF",
          dark: "#0C0C0C",
          surf: "#141414",
          cream: "#F7F4EF",
        },
      },
    },
  },
  plugins: [],
};
