import type { SessionMember } from '../../api/dungeons';
import type { MemberBusy } from '../DungeonBoard3D/boardTypes';

/*
  Party frames for a run: portrait in the ring colour of the member's figurine
  on the table, name, level, leader's crown and the four resource bars.
  `compact` is the list over the 3D table: small portraits, one under another, slim bars with numbers.
*/

type ResourceKey = 'health' | 'mana' | 'energy' | 'stamina';

const RESOURCES: { key: ResourceKey; label: string; fill: string }[] = [
  { key: 'health', label: 'Здоровье', fill: 'stat-bar-hp' },
  { key: 'mana', label: 'Мана', fill: 'stat-bar-mana' },
  { key: 'energy', label: 'Энергия', fill: 'stat-bar-energy' },
  { key: 'stamina', label: 'Выносливость', fill: 'stat-bar-stamina' },
];

const valuesOf = (m: SessionMember, key: ResourceKey): [number, number] | null => {
  const current = m[`current_${key}`];
  const max = m[`max_${key}`];
  return current == null || max == null ? null : [current, max];
};

const percentOf = ([current, max]: [number, number]) => (max > 0 ? Math.max(0, Math.min(100, (current / max) * 100)) : 0);

const Portrait = ({ member, color, size }: { member: SessionMember; color?: string; size: 'sm' | 'md' }) => {
  const dead = member.status === 'dead';
  const box = size === 'md' ? 'w-12 h-12' : 'w-9 h-9';
  return (
    <div
      className={`relative shrink-0 rounded-full p-[2px] ${box}`}
      style={{ background: color ?? 'rgba(255,255,255,0.25)' }}
    >
      {member.avatar ? (
        <img
          src={member.avatar}
          alt=""
          className={`w-full h-full rounded-full object-cover ${dead ? 'grayscale opacity-50' : ''}`}
        />
      ) : (
        <div
          className={`w-full h-full rounded-full bg-black/80 flex items-center justify-center text-white/70 ${
            size === 'md' ? 'text-base' : 'text-xs'
          } ${dead ? 'opacity-50' : ''}`}
        >
          {member.name.slice(0, 1)}
        </div>
      )}
      {member.is_leader && (
        <span className="absolute -top-1.5 -right-1 text-[11px] leading-none" title="Лидер" aria-label="Лидер">
          👑
        </span>
      )}
      {member.level != null && size === 'md' && (
        <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 px-1.5 rounded-full bg-black/90 border border-gold/40 text-gold text-[9px] leading-[14px] font-medium tabular-nums">
          {member.level}
        </span>
      )}
    </div>
  );
};

/** A thin bar for the phone strip: dark track, coloured fill, no outline. */
const Bar = ({ values, fill }: { values: [number, number]; fill: string }) => (
  <div className="relative h-1.5 rounded-full bg-white/15 overflow-hidden">
    <div
      className={`absolute inset-y-0 left-0 rounded-full ${fill} transition-[width] duration-500 ease-site`}
      style={{ width: `${percentOf(values)}%` }}
    />
  </div>
);

interface PartyFramesProps {
  members: SessionMember[];
  currentCharacterId: number | null;
  /** Figurine colour per character, so a frame and its pawn are easy to match. */
  colors?: Map<number, string>;
  compact?: boolean;
  /** Who is in a minigame right now, and which. */
  busy?: Map<number, MemberBusy>;
}

/** The line under a busy member's name. */
const BusyLine = ({ busy, small }: { busy: MemberBusy; small?: boolean }) => (
  <span className={`flex items-center gap-1 min-w-0 text-gold/90 leading-none ${small ? 'text-[10px]' : 'text-[11px]'}`}>
    <span className="animate-pulse shrink-0">{busy.icon}</span>
    <span className="truncate">{busy.text}…</span>
  </span>
);

const PartyFrames = ({ members, currentCharacterId, colors, compact = false, busy }: PartyFramesProps) => {
  if (compact) {
    // Over the table: one under another, slim bars with their numbers.
    return (
      <div className="flex flex-col gap-1.5 w-full max-w-[300px]">
        {members.map((m) => {
          const dead = m.status === 'dead';
          return (
            <div
              key={m.character_id}
              className={`flex items-center gap-2 bg-black/70 backdrop-blur-sm rounded-card pl-1.5 pr-2.5 py-1.5 border ${
                m.character_id === currentCharacterId ? 'border-gold/30' : 'border-transparent'
              }`}
            >
              <Portrait member={m} color={colors?.get(m.character_id)} size="sm" />
              <div className="flex-1 min-w-0 flex flex-col gap-[3px]">
                <div className="flex items-baseline gap-1.5 min-w-0">
                  <span className={`text-xs leading-none truncate ${dead ? 'text-white/40 line-through' : 'text-white/90'}`}>
                    {m.name}
                  </span>
                  {m.level != null && <span className="text-gold/70 text-[10px] leading-none shrink-0">{m.level} ур.</span>}
                  {m.character_id === currentCharacterId && (
                    <span className="text-white/40 text-[10px] leading-none shrink-0">вы</span>
                  )}
                  {dead && <span className="ml-auto text-site-red text-[10px] leading-none uppercase shrink-0">Пал</span>}
                </div>
                {!dead && busy?.get(m.character_id) && <BusyLine busy={busy.get(m.character_id)!} small />}
                {RESOURCES.map((r) => {
                  const values = valuesOf(m, r.key);
                  if (!values) return null;
                  return (
                    <div key={r.key} className="flex items-center gap-1.5" title={`${r.label}: ${values[0]} из ${values[1]}`}>
                      <div className="flex-1 min-w-0">
                        <Bar values={values} fill={r.fill} />
                      </div>
                      <span className="w-[58px] shrink-0 text-right text-[9px] leading-none text-white/70 font-mono tabular-nums">
                        {values[0]}/{values[1]}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {members.map((m) => {
        const dead = m.status === 'dead';
        return (
          <div
            key={m.character_id}
            className={`flex gap-3 bg-black/70 backdrop-blur-sm rounded-card p-2.5 border ${
              m.character_id === currentCharacterId ? 'border-gold/30' : 'border-white/5'
            }`}
          >
            <Portrait member={m} color={colors?.get(m.character_id)} size="md" />
            <div className="flex-1 min-w-0 flex flex-col gap-1">
              <div className="flex items-baseline gap-2 min-w-0">
                <span className={`text-sm truncate ${dead ? 'text-white/40 line-through' : 'text-white'}`}>{m.name}</span>
                {m.character_id === currentCharacterId && <span className="text-white/40 text-[11px] shrink-0">вы</span>}
                {dead && <span className="ml-auto text-site-red text-[11px] uppercase shrink-0">Пал</span>}
              </div>
              {!dead && busy?.get(m.character_id) && <BusyLine busy={busy.get(m.character_id)!} />}
              {RESOURCES.map((r) => {
                const values = valuesOf(m, r.key);
                if (!values) return null;
                return (
                  <div
                    key={r.key}
                    className="relative h-4 rounded-full bg-black/60 border border-white/15 overflow-hidden"
                    title={`${r.label}: ${values[0]} из ${values[1]}`}
                  >
                    <div
                      className={`absolute inset-y-0 left-0 ${r.fill} opacity-80 transition-[width] duration-500 ease-site`}
                      style={{ width: `${percentOf(values)}%` }}
                    />
                    <div className="relative h-full flex items-center justify-between px-2 text-[10px] leading-none text-white [text-shadow:0_1px_2px_rgba(0,0,0,0.95)]">
                      <span>{r.label}</span>
                      <span className="font-mono tabular-nums">
                        {values[0]} / {values[1]}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default PartyFrames;
