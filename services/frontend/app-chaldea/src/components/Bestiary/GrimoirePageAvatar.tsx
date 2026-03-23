import type { BestiaryEntry } from '../../api/bestiary';
import { titleFont, scriptFont, statFont } from './GrimoireBook';

const TIER_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  normal: { label: 'Обычный', color: '#5a4a2a', bg: 'rgba(139,105,20,0.1)' },
  elite: { label: 'Элитный', color: '#6a3a8a', bg: 'rgba(106,58,138,0.12)' },
  boss: { label: 'Босс', color: '#8b2020', bg: 'rgba(139,32,32,0.12)' },
};

interface GrimoirePageAvatarProps {
  entry: BestiaryEntry;
}

const SilhouettePlaceholder = () => (
  <div className="w-full h-full flex items-center justify-center relative"
    style={{ background: 'rgba(180,160,120,0.2)' }}
  >
    <span
      className="text-7xl sm:text-8xl font-bold select-none"
      style={{ fontFamily: titleFont, color: 'rgba(120,90,40,0.15)' }}
    >
      ?
    </span>
    <div
      className="absolute inset-0 opacity-[0.05]"
      style={{
        backgroundImage:
          'repeating-linear-gradient(45deg, transparent, transparent 8px, rgba(100,70,30,1) 8px, rgba(100,70,30,1) 9px), ' +
          'repeating-linear-gradient(-45deg, transparent, transparent 8px, rgba(100,70,30,1) 8px, rgba(100,70,30,1) 9px)',
      }}
    />
  </div>
);

const TierBadge = ({ tier }: { tier: string }) => {
  const config = TIER_CONFIG[tier] ?? TIER_CONFIG.normal;
  return (
    <span
      className="inline-block px-3 py-0.5 rounded-sm text-[10px] sm:text-xs tracking-widest uppercase"
      style={{
        fontFamily: statFont,
        color: config.color,
        background: config.bg,
        border: `1px solid ${config.color}30`,
      }}
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
          <path d="M2 20 L2 2 L20 2" stroke="#8b6914" strokeWidth="1.5" strokeOpacity="0.3" strokeLinecap="round" />
          <path d="M6 14 L6 6 L14 6" stroke="#8b6914" strokeWidth="0.8" strokeOpacity="0.15" strokeLinecap="round" />
          <circle cx="2" cy="2" r="2" fill="#8b6914" fillOpacity="0.2" />
        </svg>
      </div>

      {/* Avatar frame */}
      <div className="relative w-44 h-44 sm:w-52 sm:h-52 md:w-60 md:h-60">
        {/* Outer frame — ink-drawn look */}
        <div
          className="absolute inset-0 rounded-[2px]"
          style={{
            border: '2px solid rgba(100,70,30,0.35)',
            boxShadow: 'inset 0 0 4px rgba(100,70,30,0.2), 0 2px 6px rgba(100,70,30,0.15)',
          }}
        />
        {/* Inner frame */}
        <div
          className="absolute inset-[4px] rounded-[1px]"
          style={{ border: '1px solid rgba(100,70,30,0.2)' }}
        />
        {/* Corner brackets */}
        <div className="absolute -top-1.5 -left-1.5 w-4 h-4 border-t-2 border-l-2 border-amber-800/40" />
        <div className="absolute -top-1.5 -right-1.5 w-4 h-4 border-t-2 border-r-2 border-amber-800/40" />
        <div className="absolute -bottom-1.5 -left-1.5 w-4 h-4 border-b-2 border-l-2 border-amber-800/40" />
        <div className="absolute -bottom-1.5 -right-1.5 w-4 h-4 border-b-2 border-r-2 border-amber-800/40" />
        {/* Ink drip */}
        <div
          className="absolute -bottom-3 left-3 w-1 h-3 rounded-b-full"
          style={{ background: 'linear-gradient(to bottom, rgba(100,70,30,0.25), rgba(100,70,30,0.05))' }}
        />
        {/* Image */}
        <div className="absolute inset-[6px] overflow-hidden rounded-[1px]"
          style={{ background: 'rgba(190,170,130,0.3)' }}
        >
          {entry.avatar ? (
            <img
              src={entry.avatar}
              alt={entry.name}
              className="w-full h-full object-cover"
              style={{ filter: 'sepia(0.2) contrast(1.05) brightness(0.95)' }}
            />
          ) : (
            <SilhouettePlaceholder />
          )}
          {/* Soft vignette */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{ boxShadow: 'inset 0 0 15px rgba(100,70,30,0.25)' }}
          />
        </div>
      </div>

      {/* Name — medieval font */}
      <h2
        className="text-xl sm:text-2xl md:text-3xl text-center"
        style={{
          fontFamily: titleFont,
          color: '#3a2810',
          textShadow: '0 1px 2px rgba(100,70,30,0.15)',
        }}
      >
        {entry.name}
      </h2>

      {/* Tier + Level */}
      <div className="flex items-center gap-3">
        <TierBadge tier={entry.tier} />
        <span
          className="text-xs sm:text-sm"
          style={{ fontFamily: scriptFont, color: '#6a5030' }}
        >
          Уровень {entry.level}
        </span>
      </div>

      {/* Decorative bottom corner */}
      <div className="absolute bottom-3 right-3">
        <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M38 20 L38 38 L20 38" stroke="#8b6914" strokeWidth="1.5" strokeOpacity="0.3" strokeLinecap="round" />
          <path d="M34 26 L34 34 L26 34" stroke="#8b6914" strokeWidth="0.8" strokeOpacity="0.15" strokeLinecap="round" />
          <circle cx="38" cy="38" r="2" fill="#8b6914" fillOpacity="0.2" />
        </svg>
      </div>
    </div>
  );
};

export default GrimoirePageAvatar;
