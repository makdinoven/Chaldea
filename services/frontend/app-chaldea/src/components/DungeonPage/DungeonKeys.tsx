import { keyInfo } from './dungeonConstants';

/** A small key drawn in the key's colour. */
export const KeyGlyph = ({ color, className = 'w-4 h-4' }: { color: string; className?: string }) => (
  <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
    <circle cx="7" cy="12" r="4.2" fill="none" stroke={color} strokeWidth="2.4" />
    <path d="M11 12h10M17 12v4M20 12v3" fill="none" stroke={color} strokeWidth="2.4" strokeLinecap="round" />
  </svg>
);

/** The keys the party has found this run. */
const DungeonKeys = ({ keys }: { keys: string[] }) => {
  if (keys.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mb-2">
      {keys.map((kind) => {
        const key = keyInfo(kind);
        return (
          <span
            key={kind}
            className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-white/80"
          >
            <KeyGlyph color={key.color} className="w-3.5 h-3.5" />
            {key.name}
          </span>
        );
      })}
    </div>
  );
};

export default DungeonKeys;
