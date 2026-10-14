interface TurnSealProps {
  disabled: boolean;
  /** A skill or item is queued — the seal glows to invite the click. */
  armed: boolean;
  controlled: boolean;
  onClick: () => void;
}

const RUNE_COUNT = 24;

/** Rune ring drawn as SVG so it stays crisp at any size. */
const RuneRing = () => (
  <svg viewBox="0 0 100 100" className="absolute inset-0 h-full w-full animate-spin-rune" aria-hidden>
    <circle cx="50" cy="50" r="47" fill="none" stroke="rgba(240,217,92,0.55)" strokeWidth="1" />
    <circle cx="50" cy="50" r="40" fill="none" stroke="rgba(240,217,92,0.35)" strokeWidth="0.6" />
    {Array.from({ length: RUNE_COUNT }, (_, i) => {
      const a = (i / RUNE_COUNT) * Math.PI * 2;
      const x = 50 + Math.cos(a) * 43.5;
      const y = 50 + Math.sin(a) * 43.5;
      const deg = (a * 180) / Math.PI + 90;
      const shape = i % 3;
      return (
        <g key={i} transform={`translate(${x} ${y}) rotate(${deg})`} stroke="rgba(240,217,92,0.75)" strokeWidth="0.7" fill="none">
          <line x1="0" y1="-2" x2="0" y2="2" />
          {shape === 0 && <line x1="0" y1="-1" x2="1.4" y2="-2" />}
          {shape === 1 && <line x1="-1.2" y1="0" x2="1.2" y2="0" />}
          {shape === 2 && <line x1="-1.2" y1="-1.5" x2="1.2" y2="1.5" />}
        </g>
      );
    })}
  </svg>
);

const TurnSeal = ({ disabled, armed, controlled, onClick }: TurnSealProps) => {
  const label = disabled ? "Ожидание" : controlled ? "Пропустить ход" : "Передать ход";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`group relative h-[76px] w-[76px] shrink-0 rounded-full transition-all duration-300 ease-site sm:h-[104px] sm:w-[104px] ${
        disabled ? "cursor-not-allowed opacity-50 grayscale" : "cursor-pointer hover:scale-[1.04]"
      } ${armed && !disabled ? "animate-seal-glow" : ""}`}
    >
      <RuneRing />
      <span
        className={`absolute inset-[13%] flex items-center justify-center rounded-full border border-gold/50 px-1 text-center
          bg-[radial-gradient(circle_at_50%_30%,#5a4520_0%,#2a1d0e_55%,#120c06_100%)]
          shadow-[inset_0_2px_6px_rgba(255,230,150,0.25),inset_0_-4px_10px_rgba(0,0,0,0.7),0_4px_14px_rgba(0,0,0,0.6)]
          transition-colors duration-200 ${!disabled ? "group-hover:border-gold-light" : ""}`}
      >
        <span className="gold-text text-[9px] font-medium uppercase leading-tight tracking-wider sm:text-xs">
          {label}
        </span>
      </span>
    </button>
  );
};

export default TurnSeal;
