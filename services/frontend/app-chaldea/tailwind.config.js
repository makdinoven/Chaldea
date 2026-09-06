/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        montserrat: ['Montserrat', 'sans-serif'],
        mono: ['Anonymous Pro', 'monospace'],
        // Lore / book surfaces (FEAT-154). Both faces are already loaded by
        // index.html — do not add another font link.
        lore: ['MedievalSharp', 'Georgia', 'serif'],
        serif: ['"Cormorant Garamond"', 'Georgia', 'serif'],
      },
      maxWidth: {
        // Site-wide content container width (FEAT-148). Use `max-w-container`
        // instead of hardcoded pixel values for page/header wrappers.
        container: '1360px',
      },
      colors: {
        gold: {
          light: '#fff9b8',
          DEFAULT: '#f0d95c',
          dark: '#bcab4c',
        },
        site: {
          blue: '#76a6bd',
          red: '#F37753',
          bg: 'rgba(9, 10, 16, 0.62)',
          dark: '#1a1a2e',
        },
        input: '#c6c4c4',
        // Lore / book surfaces (FEAT-154): parchment paper + ink writing.
        // Only for book-like surfaces (passport, Archive), never for the dark UI.
        parchment: {
          light: '#faf1dc',
          DEFAULT: '#f5e6c8',
          dark: '#e3d0aa',
        },
        ink: {
          DEFAULT: '#3b2f1c',
          muted: '#6b5a3e',
        },
        rarity: {
          common: '#FFFFFF',
          rare: '#76A6BD',
          epic: '#B875BD',
          mythical: '#F0695B',
          legendary: '#F0D95C',
        },
        stat: {
          hp: '#E94545',
          mana: '#76A6BD',
          energy: '#88B332',
          stamina: '#FFF9B8',
        },
      },
      borderRadius: {
        'card': '15px',
        'card-lg': '20px',
        'card-xl': '29px',
        'map': '40px',
      },
      boxShadow: {
        'card': '4px 6px 4px 0 rgba(0, 0, 0, 0.25)',
        'hover': '0 8px 10px rgba(0, 0, 0, 0.15), 0 4px 6px rgba(0, 0, 0, 0.1)',
        'pressed': '0 2px 4px rgba(0, 0, 0, 0.2), 0 1px 2px rgba(0, 0, 0, 0.1)',
        'modal': '0 0 12px rgba(0, 0, 0, 0.2)',
        'dropdown': '0 4px 8px rgba(0, 0, 0, 0.3)',
        // Parchment page: aged inner vignette + outer lift (FEAT-154)
        'page': 'inset 0 0 40px rgba(90, 66, 30, 0.18), 4px 6px 10px rgba(0, 0, 0, 0.35)',
      },
      transitionDuration: {
        '200': '200ms',
      },
      transitionTimingFunction: {
        'site': 'ease-in-out',
      },
      keyframes: {
        'fade-in': {
          from: { transform: 'scale(0.95)', opacity: '0' },
          to: { transform: 'scale(1)', opacity: '1' },
        },
        'spin-slow': {
          from: { transform: 'rotate(0deg)' },
          to: { transform: 'rotate(360deg)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.2s ease-out',
        'spin-slow': 'spin-slow 2s linear infinite',
      },
    },
  },
  plugins: [],
}
