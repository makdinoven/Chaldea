import type { BestiaryEntry } from '../../api/bestiary';

const serifFont = "'Georgia', 'Palatino Linotype', 'Palatino', 'Times New Roman', serif";

const TIER_CONFIG: Record<string, { label: string; classes: string }> = {
  normal: {
    label: 'Обычный',
    classes: 'bg-amber-900/40 text-amber-200/70 border border-amber-200/20',
  },
  elite: {
    label: 'Элитный',
    classes: 'bg-purple-900/50 text-purple-200 border border-purple-400/30',
  },
  boss: {
    label: 'Босс',
    classes: 'bg-gradient-to-r from-red-900/50 to-amber-900/50 text-amber-100 border border-gold/30',
  },
};

interface GrimoirePageAvatarProps {
  entry: BestiaryEntry;
}

const SilhouettePlaceholder = () => (
  <div className="w-full h-full flex items-center justify-center bg-black/20 relative">
    <span
      className="text-amber-200/8 text-7xl sm:text-8xl font-bold select-none"
      style={{ fontFamily: serifFont }}
    >
      ?
    </span>
    {/* Cross-hatch sketch lines */}
    <div
      className="absolute inset-0 opacity-[0.03]"
      style={{
        backgroundImage:
          'repeating-linear-gradient(45deg, transparent, transparent 8px, rgba(180,150,80,1) 8px, rgba(180,150,80,1) 9px), ' +
          'repeating-linear-gradient(-45deg, transparent, transparent 8px, rgba(180,150,80,1) 8px, rgba(180,150,80,1) 9px)',
      }}
    />
  </div>
);

const TierBadge = ({ tier }: { tier: string }) => {
  const config = TIER_CONFIG[tier] ?? TIER_CONFIG.normal;
  return (
    <span
      className={`inline-block px-3 py-0.5 rounded-sm text-[10px] sm:text-xs tracking-widest uppercase ${config.classes}`}
      style={{ fontFamily: serifFont }}
    >
      {config.label}
    </span>
  );
};

const GrimoirePageAvatar = ({ entry }: GrimoirePageAvatarProps) => {
  return (
    <div className="flex flex-col items-center justify-center gap-4 sm:gap-5 p-5 sm:p-7 h-full relative">
      {/* Decorative top corner */}
      <div className="absolute top-3 left-3">
        <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M2 20 L2 2 L20 2" stroke="#c9a84c" strokeWidth="1.5" strokeOpacity="0.3" strokeLinecap="round" />
          <path d="M6 14 L6 6 L14 6" stroke="#c9a84c" strokeWidth="0.8" strokeOpacity="0.15" strokeLinecap="round" />
          <circle cx="2" cy="2" r="2" fill="#c9a84c" fillOpacity="0.2" />
        </svg>
      </div>

      {/* Avatar in ornamental frame */}
      <div className="relative w-44 h-44 sm:w-52 sm:h-52 md:w-60 md:h-60">
        {/* Outer engraved border */}
        <div
          className="absolute inset-0 rounded-[2px]"
          style={{
            border: '2px solid rgba(201,168,76,0.25)',
            boxShadow:
              'inset 0 0 6px rgba(0,0,0,0.6), 0 0 8px rgba(0,0,0,0.4), 0 0 1px rgba(201,168,76,0.15)',
          }}
        />
        {/* Inner decorative border */}
        <div
          className="absolute inset-[4px] rounded-[1px]"
          style={{
            border: '1px solid rgba(201,168,76,0.15)',
            boxShadow: 'inset 0 0 3px rgba(0,0,0,0.3)',
          }}
        />
        {/* Corner L-brackets */}
        <div className="absolute -top-1.5 -left-1.5 w-4 h-4 border-t-2 border-l-2 border-gold/40" />
        <div className="absolute -top-1.5 -right-1.5 w-4 h-4 border-t-2 border-r-2 border-gold/40" />
        <div className="absolute -bottom-1.5 -left-1.5 w-4 h-4 border-b-2 border-l-2 border-gold/40" />
        <div className="absolute -bottom-1.5 -right-1.5 w-4 h-4 border-b-2 border-r-2 border-gold/40" />
        {/* Ink drip */}
        <div
          className="absolute -bottom-3 left-3 w-1 h-3 rounded-b-full"
          style={{
            background: 'linear-gradient(to bottom, rgba(201,168,76,0.2), rgba(201,168,76,0.05))',
          }}
        />
        {/* Image area */}
        <div className="absolute inset-[6px] overflow-hidden rounded-[1px] bg-black/30">
          {entry.avatar ? (
            <img
              src={entry.avatar}
              alt={entry.name}
              className="w-full h-full object-cover"
              style={{ filter: 'sepia(0.15) contrast(1.08) brightness(0.92)' }}
            />
          ) : (
            <SilhouettePlaceholder />
          )}
          {/* Vignette over image */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              boxShadow: 'inset 0 0 20px rgba(0,0,0,0.5), inset 0 0 40px rgba(0,0,0,0.2)',
            }}
          />
        </div>
      </div>

      {/* Name */}
      <div className="relative px-6 py-1.5">
        <h2
          className="font-bold tracking-[0.08em] text-xl sm:text-2xl md:text-3xl uppercase text-center"
          style={{
            fontFamily: serifFont,
            background: 'linear-gradient(180deg, #f0dfa0 0%, #d4b050 40%, #b08830 70%, #906820 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.7))',
          }}
        >
          {entry.name}
        </h2>
      </div>

      {/* Tier + Level */}
      <div className="flex items-center gap-3">
        <TierBadge tier={entry.tier} />
        <span
          className="text-amber-200/60 text-xs sm:text-sm italic"
          style={{ fontFamily: serifFont }}
        >
          Уровень {entry.level}
        </span>
      </div>

      {/* Decorative bottom corner */}
      <div className="absolute bottom-3 right-3">
        <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M38 20 L38 38 L20 38" stroke="#c9a84c" strokeWidth="1.5" strokeOpacity="0.3" strokeLinecap="round" />
          <path d="M34 26 L34 34 L26 34" stroke="#c9a84c" strokeWidth="0.8" strokeOpacity="0.15" strokeLinecap="round" />
          <circle cx="38" cy="38" r="2" fill="#c9a84c" fillOpacity="0.2" />
        </svg>
      </div>
    </div>
  );
};

export default GrimoirePageAvatar;
