import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { ChatEntry } from '../../api/dungeons';

/*
  The run's chat and log (FEAT-176): the party's lines, and between them the
  log — moves, traps and damage, battles, who is doing what — in quiet grey
  (green when it went well, red when it went badly). New lines scroll in at
  the bottom unless the reader has scrolled up to look back.
*/

const MAX_LEN = 300;
/** Close enough to the bottom to keep following new lines. */
const STICK_PX = 40;

const time = (ms: number) =>
  new Date(ms).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });

const TONE: Record<ChatEntry['tone'], string> = {
  info: 'text-white/50',
  good: 'text-green-300/80',
  bad: 'text-site-red/90',
};

interface DungeonChatProps {
  entries: ChatEntry[];
  /** Pawn colours by character, to colour names as on the table. */
  colors?: Map<number, string>;
  currentCharacterId: number | null;
  /** Sends a line; resolves false when it could not be sent (the error is already shown). */
  onSay: (text: string) => Promise<boolean>;
  /** A member of the run who may write (a finished run is read-only). */
  canWrite: boolean;
  /** Fill the height given (a tab), instead of a fixed one. */
  fill?: boolean;
}

const DungeonChat = ({ entries, colors, currentCharacterId, onSay, canWrite, fill = false }: DungeonChatProps) => {
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const list = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    const el = list.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [entries.length]);

  const send = async (e: FormEvent) => {
    e.preventDefault();
    const line = text.trim();
    if (!line || sending) return;
    setSending(true);
    const ok = await onSay(line);
    setSending(false);
    if (ok) {
      setText('');
      stick.current = true;
    }
  };

  return (
    <div className={`flex flex-col gap-2 min-h-0 ${fill ? 'h-full' : 'h-[50vh] lg:h-[420px]'}`}>
      <div
        ref={list}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_PX;
        }}
        className="flex-1 min-h-0 overflow-y-auto gold-scrollbar flex flex-col gap-1.5 pr-1"
      >
        {entries.length === 0 && <p className="text-white/40 text-xs text-center py-6">Пока тихо.</p>}
        {entries.map((e) =>
          e.kind === 'say' ? (
            <div key={e.id} className="text-sm leading-snug break-words">
              <span className="text-white/30 text-[10px] tabular-nums mr-1.5">{time(e.at)}</span>
              <span
                className="font-medium mr-1"
                style={{ color: (e.character_id !== null && colors?.get(e.character_id)) || '#d6b46a' }}
              >
                {e.name}
                {e.character_id === currentCharacterId ? ' (вы)' : ''}:
              </span>
              <span className="text-white/90">{e.text}</span>
            </div>
          ) : (
            <div key={e.id} className={`text-xs leading-snug break-words ${TONE[e.tone] ?? TONE.info}`}>
              <span className="text-white/25 text-[10px] tabular-nums mr-1.5">{time(e.at)}</span>
              {e.text}
            </div>
          ),
        )}
      </div>
      {canWrite && (
        <form onSubmit={(e) => void send(e)} className="flex gap-2 shrink-0">
          <input
            value={text}
            onChange={(e) => setText(e.target.value.slice(0, MAX_LEN))}
            maxLength={MAX_LEN}
            placeholder="Сказать отряду…"
            className="input-underline flex-1 min-w-0 !text-sm"
            aria-label="Сообщение отряду"
          />
          <button
            type="submit"
            disabled={sending || !text.trim()}
            className="btn-blue text-sm px-4 py-1.5 shrink-0 disabled:opacity-50"
          >
            Сказать
          </button>
        </form>
      )}
    </div>
  );
};

export default DungeonChat;
