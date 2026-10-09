/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Iowan Old Style", "Palatino Linotype", "Georgia", "serif"],
      },
      colors: {
        ink: "#343a33",
        mist: "#f5f2eb",
        sage: "#647c67",
        clay: "#bd795f",
      },
      boxShadow: {
        soft: "0 18px 45px rgba(59, 61, 51, 0.06)",
      },
    },
  },
  plugins: [require("daisyui")],
  daisyui: {
    themes: ["light"],
    logs: false,
  },
};
