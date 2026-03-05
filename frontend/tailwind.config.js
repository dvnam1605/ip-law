/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./services/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
      animation: {
        'bounce-slow': 'bounce 1.5s infinite',
      },
    },
  },
  plugins: [],
}
