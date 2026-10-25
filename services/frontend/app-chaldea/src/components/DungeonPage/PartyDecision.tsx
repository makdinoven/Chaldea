import type { BoardPingKind, SessionState } from '../../api/dungeons';

/*
  The party decides together where to go. Everyone living says where they
  would go — a door (a click on the table or the map), the blue portal, or
  "as the leader decides" — and the leader can lead on only once all have had
  their say. The marks tools let anyone flash a sign over a room.
*/

interface PartyDecisionProps {
  session: SessionState;
  characterId: number | null;
  isLeader: boolean;
  colors: Map<number, string>;
  /** The current room has a blue portal to step into. */
  portalHere: boolean;
  voting: boolean;
  onVote: (choice: { corridorId?: number; portal?: boolean }) => void;
  /** Over the 3D table: a translucent card. */
  overBoard?: boolean;
}

const UNKNOWN_ROOM = '???';

export const PartyDecision = ({
  session,
  characterId,
  isLeader,
  colors,
  portalHere,
  voting,
  onVote,
  overBoard = false,
}: PartyDecisionProps) => {
  const alive = session.members.filter((m) => m.status === 'alive');
  if (alive.length < 2) return null;
  const votes = new Map((session.votes ?? []).map((v) => [v.character_id, v]));
  const waiting = new Set(session.waiting_for ?? []);
  const exits = new Map((session.current_room?.exits ?? []).map((e) => [e.corridor_id, e]));
  const me = alive.find((m) => m.character_id === characterId);
  const myVote = me ? votes.get(me.character_id) : undefined;

  const say = (memberId: number, leader: boolean) => {
    if (leader) return 'ведёт отряд';
    const v = votes.get(memberId);
    if (!v) return 'думает…';
    if (v.portal) return '→ в портал';
    if (v.corridor_id) {
      const exit = exits.get(v.corridor_id);
      const name = exit && exit.to_room_name !== UNKNOWN_ROOM ? `«${exit.to_room_name}»` : 'в неизведанное';
      return `→ ${name}`;
    }
    return 'как решит лидер';
  };

  return (
    <div
      className={`rounded-card border border-white/10 p-3 flex flex-col gap-2 ${
        overBoard ? 'bg-black/60 backdrop-blur-sm' : 'bg-black/40'
      }`}
    >
      <p className="gold-text text-sm font-medium uppercase">Куда идём?</p>
      <ul className="flex flex-col gap-1">
        {alive.map((m) => {
          const leader = m.is_leader;
          const thinking = !leader && waiting.has(m.character_id);
          return (
            <li key={m.character_id} className="flex items-center gap-2 text-xs min-w-0">
              <span
                className="w-2.5 h-2.5 rounded-full shrink-0"
                style={{ background: colors.get(m.character_id) ?? 'rgba(255,255,255,0.4)' }}
              />
              <span className="text-white truncate">{m.name}</span>
              <span className={`ml-auto shrink-0 ${thinking ? 'text-white/40 animate-pulse' : 'text-white/70'}`}>
                {say(m.character_id, leader)}
              </span>
            </li>
          );
        })}
      </ul>
      {isLeader ? (
        <p className={`text-xs ${waiting.size ? 'text-white/50' : 'text-green-300/90'}`}>
          {waiting.size ? 'Идти можно, когда выскажутся все.' : 'Отряд высказался — ведите.'}
        </p>
      ) : me ? (
        <>
          <p className="hidden sm:block text-white/50 text-xs">
            {myVote ? 'Можно передумать: ' : ''}нажмите на соседнюю комнату, чтобы предложить путь.
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={voting}
              onClick={() => onVote({})}
              className="btn-line text-xs px-3 py-1.5 disabled:opacity-50"
            >
              Как решит лидер
            </button>
            {portalHere && (
              <button
                type="button"
                disabled={voting}
                onClick={() => onVote({ portal: true })}
                className="btn-line text-xs px-3 py-1.5 disabled:opacity-50"
              >
                В портал
              </button>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
};

const MARK_TOOLS: { kind: BoardPingKind; label: string; sign: string }[] = [
  { kind: 'go', label: 'Сюда', sign: '↓' },
  { kind: 'danger', label: 'Опасно', sign: '!' },
  { kind: 'look', label: 'Смотрите', sign: '◉' },
];

/** Buttons to flash a sign over a room: pick one, then tap the room. */
export const MarkTools = ({
  armed,
  onArm,
}: {
  armed: BoardPingKind | null;
  onArm: (kind: BoardPingKind | null) => void;
}) => (
  <div className="flex flex-col gap-1 items-end lg:items-start">
    <div className="flex items-center gap-1.5">
      {MARK_TOOLS.map((t) => (
        <button
          key={t.kind}
          type="button"
          title={t.label}
          aria-label={`Метка: ${t.label}`}
          aria-pressed={armed === t.kind}
          onClick={() => onArm(armed === t.kind ? null : t.kind)}
          className={`h-9 px-3 rounded-full backdrop-blur-sm text-xs whitespace-nowrap transition-colors duration-200 ease-site ${
            armed === t.kind ? 'bg-gold/30 text-gold' : 'bg-black/60 text-white/80 hover:text-site-blue'
          }`}
        >
          <span className="mr-1" aria-hidden>
            {t.sign}
          </span>
          {t.label}
        </button>
      ))}
    </div>
    {armed && <p className="text-white/70 text-xs bg-black/60 rounded-card px-2 py-1">Нажмите на комнату или дверь</p>}
  </div>
);
