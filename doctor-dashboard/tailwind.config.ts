import type { Config } from 'tailwindcss'

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '#1A56DB',
        secondary: '#0694A2',
        'bg-app': '#F0F4F8',
        card: '#FFFFFF',
        'text-navy': '#1A2B4A',
        'text-muted': '#6B7280',
        'border-subtle': '#CBD5E1',
        success: '#10B981',
        warning: '#F59E0B',
        urgent: '#EF4444',
      }
    },
  },
  plugins: [],
} satisfies Config
