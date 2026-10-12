/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,jsx,ts,tsx}", "./components/**/*.{js,jsx,ts,tsx}"],
  presets: [require("nativewind/preset")],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        primary: "#1A56DB",
        secondary: "#0694A2",
        background: "#F0F4F8",
        card: "#FFFFFF",
        textPrimary: "#1A2B4A",
        textSecondary: "#6B7280",
        border: "#CBD5E1",
        success: "#10B981",
        warning: "#F59E0B",
        urgent: "#EF4444",
        urgencyRoutine: "#10B981",
        urgencySoon: "#F59E0B",
        urgencyUrgent: "#EF4444"
      }
    },
  },
  plugins: [],
}
