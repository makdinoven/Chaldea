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
        // "Pass turn" seal in the 3D battle HUD
        'seal-glow': {
          '0%, 100%': { boxShadow: '0 0 14px rgba(240,217,92,0.35)' },
          '50%': { boxShadow: '0 0 30px rgba(240,217,92,0.75)' },
        },
        // Damage / heal numbers in the 3D battle arena: slam in, settle, rise and fade
        'damage-pop': {
          '0%': { transform: 'translate(-50%, 0) scale(2.4) rotate(-10deg)', opacity: '0' },
          '10%': { transform: 'translate(-50%, 0) scale(0.88) rotate(-4deg)', opacity: '1' },
          '18%': { transform: 'translate(-50%, 0) scale(1.08) rotate(-4deg)', opacity: '1' },
          '26%': { transform: 'translate(-50%, 0) scale(1) rotate(-4deg)', opacity: '1' },
          '70%': { transform: 'translate(-50%, -28px) scale(1) rotate(-4deg)', opacity: '1' },
          '100%': { transform: 'translate(-50%, -64px) scale(0.92) rotate(-4deg)', opacity: '0' },
        },
        // A critical hit slams down from higher up, jolts, then rises like the rest
        'crit-pop': {
          '0%': { transform: 'translate(-50%, 0) scale(3.4) rotate(-14deg)', opacity: '0' },
          '9%': { transform: 'translate(-50%, 0) scale(0.82) rotate(-3deg)', opacity: '1' },
          '13%': { transform: 'translate(calc(-50% - 6px), 2px) scale(1.12) rotate(-6deg)', opacity: '1' },
          '17%': { transform: 'translate(calc(-50% + 5px), -2px) scale(1.04) rotate(-2deg)', opacity: '1' },
          '23%': { transform: 'translate(-50%, 0) scale(1) rotate(-4deg)', opacity: '1' },
          '72%': { transform: 'translate(-50%, -28px) scale(1) rotate(-4deg)', opacity: '1' },
          '100%': { transform: 'translate(-50%, -64px) scale(0.92) rotate(-4deg)', opacity: '0' },
        },
        // Liquid surface in a resource flask sliding by one wave period
        'liquid-wave': {
          '0%': { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-20px)' },
        },
        // A bubble rising through a flask and popping at the surface
        'vial-bubble': {
          '0%': { transform: 'translateY(0)', opacity: '0' },
          '15%': { opacity: '0.8' },
          '80%': { opacity: '0.6' },
          '100%': { transform: 'translateY(-24px)', opacity: '0' },
        },
        // Stars / sparks circling a stunned fighter: x and y swing a quarter-turn apart
        'orbit-x': {
          '0%, 100%': { transform: 'translateX(var(--rx, 40px))' },
          '50%': { transform: 'translateX(calc(-1 * var(--rx, 40px)))' },
        },
        'orbit-y': {
          '0%, 100%': { transform: 'translateY(var(--ry, 8px))' },
          '50%': { transform: 'translateY(calc(-1 * var(--ry, 8px)))' },
        },
        // A stunned card swaying on its feet
        'daze-sway': {
          '0%, 100%': { transform: 'rotate(-1.6deg) translateX(-1px)' },
          '50%': { transform: 'rotate(1.6deg) translateX(1px)' },
        },
        // Electrified portrait: two quick white jolts, then a long quiet
        'aura-jolt': {
          '0%, 6%, 12%, 100%': { opacity: '0' },
          '3%': { opacity: '0.35' },
          '9%': { opacity: '0.2' },
        },
        'flicker': {
          '0%, 30%, 100%': { opacity: '0' },
          '4%, 12%, 20%': { opacity: '1' },
          '8%, 16%': { opacity: '0.3' },
        },
        // A card dealt into the hand from below the table
        'hand-deal': {
          '0%': { transform: 'translateY(70px) scale(0.9)', opacity: '0' },
          '100%': { transform: 'translateY(0) scale(1)', opacity: '1' },
        },
        // The chosen card flying up out of the hand into its slot
        'card-play': {
          '0%': { transform: 'translateY(0) scale(1)', opacity: '1' },
          '35%': { transform: 'translateY(-24px) scale(1.15)', opacity: '1' },
          '100%': { transform: 'translateY(-140px) scale(0.55) rotate(-6deg)', opacity: '0' },
        },
        // A thrust / gust streaking in from the left and fading
        'thrust': {
          '0%': { transform: 'translateX(-40%) scaleX(0.3)', opacity: '0' },
          '30%': { transform: 'translateX(0) scaleX(1)', opacity: '1' },
          '100%': { transform: 'translateX(35%) scaleX(0.8)', opacity: '0' },
        },
        // A resource orb flaring as it fills
        'vial-fill': {
          '0%': { transform: 'scale(1)', opacity: '0' },
          '25%': { transform: 'scale(1.18)', opacity: '1' },
          '100%': { transform: 'scale(1)', opacity: '0' },
        },
        // "+N" drifting off a filled orb
        'gain-float': {
          '0%': { transform: 'translate(4px, -50%)', opacity: '0' },
          '15%': { transform: 'translate(0, -50%)', opacity: '1' },
          '70%': { opacity: '1' },
          '100%': { transform: 'translate(-4px, -110%)', opacity: '0' },
        },
        // A healing glint rising up the portrait
        'heal-rise': {
          '0%': { transform: 'translateY(0) scale(0.6)', opacity: '0' },
          '20%': { opacity: '1' },
          '100%': { transform: 'translateY(-90px) scale(1.1)', opacity: '0' },
        },
        // A ring of light rising from the foot of a card (buff on oneself)
        'cast-rise': {
          '0%': { transform: 'translateY(0) scale(0.6)', opacity: '0' },
          '20%': { opacity: '1' },
          '100%': { transform: 'translateY(-260%) scale(1.15)', opacity: '0' },
        },
        // A ring closing in on a card like a seal (effect cast onto it)
        'cast-seal': {
          '0%': { transform: 'scale(1.35)', opacity: '0' },
          '35%': { transform: 'scale(1)', opacity: '1' },
          '55%': { transform: 'scale(1.03)', opacity: '0.9' },
          '100%': { transform: 'scale(1)', opacity: '0' },
        },
        // A damage-over-time number: lands under the card and sinks away like a drop
        'dot-pop': {
          '0%': { transform: 'translate(-50%, -8px) scale(1.6)', opacity: '0' },
          '12%': { transform: 'translate(-50%, 0) scale(0.95)', opacity: '1' },
          '20%': { transform: 'translate(-50%, 0) scale(1)', opacity: '1' },
          '70%': { transform: 'translate(-50%, 14px) scale(1)', opacity: '1' },
          '100%': { transform: 'translate(-50%, 32px) scale(0.95)', opacity: '0' },
        },
        // Damage-over-time overlays: fade in, hold, fade out
        'fx-fade': {
          '0%': { opacity: '0' },
          '15%': { opacity: '1' },
          '70%': { opacity: '1' },
          '100%': { opacity: '0' },
        },
        // Blood running down a portrait (length per drip via --drip)
        'blood-drip': {
          '0%': { height: '0', opacity: '1' },
          '55%': { height: 'var(--drip, 50%)', opacity: '1' },
          '100%': { height: 'var(--drip, 50%)', opacity: '0' },
        },
        // A drop of blood falling off the card's lower edge
        'drop-fall': {
          '0%': { transform: 'translateY(0) scaleY(1)', opacity: '0' },
          '10%': { opacity: '1' },
          '100%': { transform: 'translateY(30px) scaleY(1.35)', opacity: '0' },
        },
        // A tongue of flame flickering up and dying down
        'flame-lick': {
          '0%': { transform: 'scaleY(0.2)', opacity: '0' },
          '15%': { transform: 'scaleY(1.1)', opacity: '1' },
          '35%': { transform: 'scaleY(0.8) scaleX(1.05)', opacity: '1' },
          '55%': { transform: 'scaleY(1.15) scaleX(0.95)', opacity: '1' },
          '75%': { transform: 'scaleY(0.9)', opacity: '0.85' },
          '100%': { transform: 'scaleY(0.3)', opacity: '0' },
        },
        // A spark rising from a fire and drifting sideways (via --dx)
        'spark-rise': {
          '0%': { transform: 'translate(0, 0)', opacity: '0' },
          '10%': { opacity: '1' },
          '100%': { transform: 'translate(var(--dx, 6px), -70px)', opacity: '0' },
        },
        // A poison bubble rising through the portrait
        'poison-bubble': {
          '0%': { transform: 'translateY(0) scale(0.5)', opacity: '0' },
          '15%': { opacity: '0.9' },
          '100%': { transform: 'translateY(-90px) scale(1.15)', opacity: '0' },
        },
        // A rune flaring as its effect ticks
        'rune-flare': {
          '0%': { transform: 'scale(0.5)', opacity: '0' },
          '25%': { transform: 'scale(1.1)', opacity: '1' },
          '100%': { transform: 'scale(1.7)', opacity: '0' },
        },
        // Blade slash across a struck card
        'slash': {
          '0%': { transform: 'rotate(-32deg) scaleX(0)', opacity: '1' },
          '35%': { transform: 'rotate(-32deg) scaleX(1)', opacity: '1' },
          '100%': { transform: 'rotate(-32deg) scaleX(1)', opacity: '0' },
        },
        'float-up': {
          '0%': { transform: 'translate(-50%, 0) scale(0.6)', opacity: '0' },
          '15%': { transform: 'translate(-50%, -10px) scale(1.15)', opacity: '1' },
          '70%': { opacity: '1' },
          '100%': { transform: 'translate(-50%, -60px) scale(1)', opacity: '0' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.2s ease-out',
        'spin-slow': 'spin-slow 2s linear infinite',
        'float-up': 'float-up 1.3s ease-out forwards',
        'damage-pop': 'damage-pop 2.3s cubic-bezier(0.2,0.8,0.3,1) forwards',
        'crit-pop': 'crit-pop 2.3s cubic-bezier(0.2,0.8,0.3,1) forwards',
        'liquid-wave': 'liquid-wave 2.4s linear infinite',
        'dot-pop': 'dot-pop 2.3s cubic-bezier(0.2,0.8,0.3,1) forwards',
        'orbit-x': 'orbit-x 2.2s ease-in-out infinite',
        'cast-rise': 'cast-rise 1.1s ease-out both',
        'vial-fill': 'vial-fill 0.9s ease-out both',
        'thrust': 'thrust 0.6s ease-out both',
        'hand-deal': 'hand-deal 0.35s cubic-bezier(0.2,0.8,0.3,1) both',
        'card-play': 'card-play 0.38s ease-in forwards',
        'flicker': 'flicker 1.4s linear infinite',
        'aura-jolt': 'aura-jolt 3.4s linear infinite',
        'gain-float': 'gain-float 1.3s ease-out both',
        'heal-rise': 'heal-rise 1.3s ease-out both',
        'cast-seal': 'cast-seal 0.9s cubic-bezier(0.2,0.8,0.3,1) both',
        'orbit-y': 'orbit-y 2.2s ease-in-out infinite',
        'daze-sway': 'daze-sway 2.6s ease-in-out infinite',
        'fx-fade': 'fx-fade 1.6s ease-out both',
        'blood-drip': 'blood-drip 1.5s cubic-bezier(0.3,0.6,0.4,1) both',
        'drop-fall': 'drop-fall 0.7s ease-in both',
        'flame-lick': 'flame-lick 1.3s ease-out both',
        'spark-rise': 'spark-rise 1s ease-out both',
        'poison-bubble': 'poison-bubble 1.4s ease-out both',
        'rune-flare': 'rune-flare 0.9s ease-out both',
        'vial-bubble': 'vial-bubble 2.6s ease-in infinite',
        'slash': 'slash 1.2s ease-out forwards',
        'seal-glow': 'seal-glow 1.8s ease-in-out infinite',
        'spin-rune': 'spin-slow 40s linear infinite',
      },
    },
  },
  plugins: [],
}
