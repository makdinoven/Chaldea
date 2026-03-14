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
          bg: 'rgba(35, 35, 41, 0.9)',
          dark: '#1a1a2e',
        },
        input: '#c6c4c4',
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
