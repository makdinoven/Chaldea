import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { fetchEscortMessages, postEscortMessage } from '../../api/caravanEscort';
import { apiErrorMessage } from '../../api/errors';
import type { EscortMessage } from '../../types/caravanEscort';
import { formatServerDateTime } from '../../utils/serverDate';

interface CaravanEscortChannelProps {
  characterId: number;
  /** The escort job ended (C5/C6 answered 404) — the parent reloads the job. */
  onNotEscort: () => void;
}

/** Backend body bound (C6, after strip). */
const TEXT_MAX = 500;
/** Poll period while the panel is open (feature file 3.16). */
const POLL_MS = 15_000;
/** Messages kept on screen. */
const KEEP_MAX = 200;
const HTTP_NOT_FOUND = 404;

const TIME_FORMAT: Intl.DateTimeFormatOptions = { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' };

const isNotFound = (err: unknown): boolean => axios.isAxiosError(err) && err.response?.status === HTTP_NOT_FOUND;

/**
 * FEAT-212 — the private caravan channel: only the escorts of this caravan read and write it.
 * Polls C5 with `after_id`; messages are plain text (React escapes them).
 */
const CaravanEscortChannel = ({ characterId, onNotEscort }: CaravanEscortChannelProps) => {
  const [messages, setMessages] = useState<EscortMessage[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const lastIdRef = useRef(0);
  const sendingRef = useRef(false);
  const listRef = useRef<HTMLDivElement | null>(null);
  /** The first failure of a poll series is toasted; repeats stay inline only. */
  const toastedRef = useRef(false);

  const poll = useCallback(async () => {
    try {
      const res = await fetchEscortMessages(characterId, lastIdRef.current);
      const fresh = res.messages ?? [];
      if (fresh.length > 0) {
        lastIdRef.current = fresh[fresh.length - 1].id;
        setMessages((prev) => {
          const known = new Set(prev.map((m) => m.id));
          return [...prev, ...fresh.filter((m) => !known.has(m.id))].slice(-KEEP_MAX);
        });
      }
      setLoadError(null);
      toastedRef.current = false;
    } catch (err) {
      if (isNotFound(err)) {
        onNotEscort();
        return;
      }
      const msg = apiErrorMessage(err, 'Не удалось загрузить караванный канал');
      setLoadError(msg);
      if (!toastedRef.current) {
        toast.error(msg);
        toastedRef.current = true;
      }
    } finally {
      setLoaded(true);
    }
  }, [characterId, onNotEscort]);

  useEffect(() => {
    lastIdRef.current = 0;
    setMessages([]);
    void poll();
    const timer = setInterval(() => void poll(), POLL_MS);
    return () => clearInterval(timer);
  }, [poll]);

  // Keep the newest message in view.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length]);

  const trimmed = text.trim();
  const canSend = trimmed.length > 0 && trimmed.length <= TEXT_MAX && !sending;

  const send = async () => {
    if (sendingRef.current || !canSend) return;
    sendingRef.current = true;
    setSending(true);
    setSendError(null);
    try {
      await postEscortMessage(characterId, trimmed);
      setText('');
      await poll();
    } catch (err) {
      if (isNotFound(err)) onNotEscort();
      const msg = apiErrorMessage(err, 'Не удалось отправить сообщение');
      setSendError(msg);
      toast.error(msg);
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  return (
    <section className="flex flex-col gap-2 min-w-0">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">Караванный канал</h3>
        <span className="text-white/40 text-[11px]">видят только охранники этого каравана</span>
      </div>
      <div
        ref={listRef}
        className="flex flex-col gap-2 max-h-[260px] min-h-[96px] overflow-y-auto gold-scrollbar rounded-card border border-white/10 bg-black/20 p-2.5"
      >
        {!loaded ? (
          <div className="m-auto w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        ) : messages.length === 0 ? (
          <p className="m-auto text-white/40 text-xs text-center">
            Пока тихо. Здесь можно договориться с другими охранниками — налётчики этого не увидят.
          </p>
        ) : (
          messages.map((m) => {
            const mine = m.character_id === characterId;
            return (
              <div key={m.id} className="flex items-start gap-2 min-w-0">
                <div className="w-7 h-7 rounded-full overflow-hidden bg-black/40 shrink-0">
                  {m.avatar ? (
                    <img src={m.avatar} alt="" className="w-full h-full object-cover" />
                  ) : (
                    <span className="w-full h-full flex items-center justify-center text-xs text-white/40" aria-hidden>
                      ?
                    </span>
                  )}
                </div>
                <div className="flex flex-col min-w-0 flex-1">
                  <span className="text-[11px] text-white/50">
                    <span className={mine ? 'text-gold' : 'text-white/80'}>{m.name ?? `#${m.character_id}`}</span>
                    {' · '}
                    {formatServerDateTime(m.created_at, TIME_FORMAT)}
                  </span>
                  <p className="text-white/90 text-sm whitespace-pre-wrap break-words">{m.body}</p>
                </div>
              </div>
            );
          })
        )}
      </div>
      {loadError && <p className="text-site-red text-xs">{loadError}</p>}
      <div className="flex flex-col sm:flex-row sm:items-end gap-2 min-w-0">
        <label className="flex flex-col gap-0.5 flex-1 min-w-0">
          <span className="sr-only">Сообщение в караванный канал</span>
          <textarea
            value={text}
            maxLength={TEXT_MAX}
            rows={2}
            disabled={sending}
            onChange={(e) => {
              setText(e.target.value);
              setSendError(null);
            }}
            onKeyDown={onKeyDown}
            placeholder="Сообщение охранникам (Enter — отправить)"
            className="w-full resize-none rounded-card border border-white/15 bg-black/30 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:border-gold/50 outline-none"
          />
          <span className={`self-end text-[11px] ${text.length >= TEXT_MAX ? 'text-site-red' : 'text-white/40'}`}>
            {text.length}/{TEXT_MAX}
          </span>
        </label>
        <button type="button" className="btn-blue w-full sm:w-auto !px-5 sm:mb-5" disabled={!canSend} onClick={() => void send()}>
          {sending ? 'Отправка...' : 'Отправить'}
        </button>
      </div>
      {sendError && <p className="text-site-red text-xs">{sendError}</p>}
    </section>
  );
};

export default CaravanEscortChannel;
