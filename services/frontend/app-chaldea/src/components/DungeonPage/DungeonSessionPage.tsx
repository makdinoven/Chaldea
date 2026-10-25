import { useEffect, useState, useCallback, useMemo, useRef, type ReactNode } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchSessionState,
  moveDungeon,
  fleeDungeonThunk,
  interactRoom,
  clearMoveResponse,
  clearDungeonState,
  clearSkippedMembers,
  selectSessionState,
  selectSessionStateError,
  selectStateLoading,
  selectMoveLoading,
  selectFleeLoading,
  selectInteractLoading,
  selectLastMoveResponse,
  selectLastFleeResponse,
  selectLastFinalizeResponse,
  selectLastSkippedMembers,
} from '../../redux/slices/dungeonSlice';
import { getMe } from '../../redux/slices/userSlice';
import { getAccessToken } from '../../api/authToken';
import {
  finishChallenge,
  getChat,
  lightRoom,
  sayChat,
  type ChatEntry,
  itemLabel,
  pingBoard,
  startChallenge,
  stepChallenge,
  voteRoute,
  type BoardPingKind,
  type ChallengeKind,
  type ChallengeResult,
  type ChallengeStart,
  type RoomSecret,
  type GateLook,
} from '../../api/dungeons';
import { getErrorMessage } from '../../redux/slices/dungeonSlice';
import type {
  RoomExit,
  RoomView,
  SessionState,
  CorridorEvent,
  MoveResponse,
  RoomEvent,
  FleeResponse,
  FinalizeResponse,
  SkippedMember,
} from '../../api/dungeons';
import type { DungeonWsMessage } from '../../hooks/useDungeonWebSocket';
import useDungeonWebSocket from '../../hooks/useDungeonWebSocket';
import useMediaQuery from '../../hooks/useMediaQuery';
import { formatServerDateTime, parseServerDate } from '../../utils/serverDate';
import DungeonMap from './DungeonMap';
import DungeonRoom from './DungeonRoom';
import DungeonPartyPanel from './DungeonPartyPanel';
import PartyFrames from './PartyFrames';
import { playDungeonSound } from '../../utils/dungeonSounds';
import DungeonInventory from './DungeonInventory';
import DungeonLootDistribution from './DungeonLootDistribution';
import ModalShell from '../CommonComponents/ModalShell/ModalShell';
import { battlePath } from '../../utils/battlePath';
import { DUNGEON_BATTLE_RETURN_KEY, ROOM_TYPE_LABELS, keyInfo } from './dungeonConstants';
import { KeyGlyph } from './DungeonKeys';
import DungeonBoardView from './DungeonBoardView';
import { setClientPrefs, useClientPrefs } from '../../utils/clientPrefs';
import { isWebGLAvailable } from '../pages/BattlePage/Arena3D/webgl';
import { boardOfFloor, createBoardMemory, membersToPawns, sessionToBoard } from '../DungeonBoard3D/sessionToBoard';
import type { MemberBusy } from '../DungeonBoard3D/boardTypes';
import { floorTheme } from '../DungeonBoard3D/dungeonThemes';
import { useBoardPresentation, type BoardMoveEvent } from '../DungeonBoard3D/useBoardPresentation';
import type { CorridorScene, FloorSpan } from '../DungeonBoard3D/DungeonBoardScene';
import DungeonChat from './DungeonChat';
import type { BoardTab } from './DungeonBoardView';
import { markRemark, voteRemark } from './remarks';
import { MARK_SECONDS, type BoardMark } from '../DungeonBoard3D/PartyMarks';
import { MarkTools, PartyDecision } from './PartyDecision';
import ChallengeModal from './minigames/ChallengeModal';

// --- Types / constants ---

/** What a room the party is done with says on hover, by kind. */
const SPENT_LABELS: Partial<Record<string, string>> = {
  treasure: 'Сундук пуст',
  rest: 'Привал использован',
  trap: 'Ловушка пройдена',
  event: 'Событие пройдено',
  teleport: 'Портал раскрыт',
};

/** Something waits to be done in this room: a chest, an event choice, a rest, a trader, the mana core. */
const roomNeedsAction = (room: RoomView, session: SessionState): boolean => {
  const cfg = room.room_config_visible ?? {};
  if (room.is_mana_core_room) return !!session.mana_core?.accessible;
  switch (room.room_type) {
    case 'treasure':
      return cfg.loot_collected !== true;
    case 'boss':
      return room.is_cleared && (cfg.loot_collected !== true || !!session.mana_core?.accessible);
    case 'event':
      return Array.isArray(cfg.choices) && cfg.choices.length > 0 && cfg.choice_made == null;
    case 'rest':
      return cfg.rest_used !== true;
    case 'merchant':
      return true;
    default:
      return false;
  }
};

type MobileTab = 'map' | 'room' | 'party' | 'chat';

const PHASE_LABELS: Record<string, string> = {
  exploring: 'Исследование',
  resting: 'Привал',
  in_battle: 'Бой',
  battle_pending: 'Враги впереди',
  distributing_loot: 'Дележ добычи',
  wiped: 'Группа пала',
  finished: 'Забег завершён',
};

/** Phases that show the map: in 3D the table stands in for it. */
/** The longest the room's news waits for the figurines if the table never reports them in. */
const ARRIVAL_FALLBACK_MS = 8000;

const MAP_PHASES = new Set<string>(['exploring', 'resting', 'battle_pending', 'in_battle']);

const STABILITY_LABELS: Record<string, string> = {
  static: 'Изученный',
  unstable: 'Нестабильный',
  chaotic: 'Хаотичный',
};

const PASSAGE_TITLES: Record<string, { down: string; up: string }> = {
  stairs: { down: 'Лестница вниз', up: 'Лестница наверх' },
  drop: { down: 'Провал', up: 'Провал' },
  lift: { down: 'Подъёмник вниз', up: 'Подъёмник наверх' },
};

const passageTitle = (exit: RoomExit, fromFloor?: number) => {
  const titles = PASSAGE_TITLES[exit.passage ?? 'stairs'] ?? PASSAGE_TITLES.stairs;
  return (exit.to_floor ?? 1) > (fromFloor ?? 1) ? titles.down : titles.up;
};

/** What a shut door wants, for the card by the cursor. */
const lockLine = (exit: RoomExit, keys: string[]) => {
  if (!exit.lock_key) return 'Заперто: открывает рычаг';
  const key = keyInfo(exit.lock_key).name.toLowerCase();
  return keys.includes(exit.lock_key) ? `Заперто — ${key} у вас есть` : `Заперто: нужен ${key}`;
};

/** WS events the leader already sees from his own HTTP response — no extra toast for him. */
const LEADER_ECHO_EVENTS = new Set([
  'room_entered', 'trap_triggered', 'battle_started', 'loot_added', 'event_result',
  'rest_started', 'rest_completed', 'mana_core_result', 'loot_distributed', 'lock_picked', 'lever_pulled',
]);

const REFRESH_DEBOUNCE_MS = 300;
const BATTLE_POLL_MS = 20000;
const MOVE_BANNER_MS = 9000;

const DATE_TIME_SHORT: Intl.DateTimeFormatOptions = {
  day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
};
const TIME_ONLY: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit' };

const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);
const obj = <T,>(v: unknown): T | null => (v && typeof v === 'object' ? (v as T) : null);

const NO_ROOMS = new Set<number>();
/** Locks are the rogue's craft (classes: 1 warrior, 2 rogue, 3 mage). */
const ROGUE_CLASS_ID = 2;

/** Each secret way out: who it suits, what to do about it, the stat a plain roll leans on. */
const SECRET_CRAFT: Record<RoomSecret['kind'], { classId: number; craft: string; action: string; stat: string; doing: string }> = {
  mechanism: { classId: 2, craft: 'плута', action: 'Искать механизм', stat: 'ловкости', doing: 'ищет скрытый механизм' },
  illusion: { classId: 3, craft: 'мага', action: 'Рассеять иллюзию', stat: 'интеллекта', doing: 'рассеивает иллюзию' },
  rubble: { classId: 1, craft: 'воина', action: 'Разобрать завал', stat: 'силы', doing: 'разбирает завал' },
};
/** The warrior's own (FEAT-176): the party shield, and gates to hold up. */
const WARRIOR_CLASS_ID = 1;
const GATE_NAMES: Record<GateLook, { name: string; acc: string }> = {
  grate: { name: 'решётка', acc: 'решётку' },
  slab: { name: 'плита', acc: 'плиту' },
};
/** A shield held perfectly takes off this share of a blow (dungeon-service SHIELD_ABSORB). */
const SHIELD_ABSORB = 0.75;
/** The mage's own (FEAT-176): seals and light; the rogue's: searching a room. */
const MAGE_CLASS_ID = 3;
/** Stamina for a light (dungeon-service LIGHT_SPELL_COST / TORCH_COST), before the dungeon's multiplier. */
const LIGHT_SPELL_COST = 1;
/** What a scout calls the room ahead, by its kind. */
const ROOM_KIND_NAMES: Record<string, string> = {
  battle: 'бой',
  boss: 'логово босса',
  treasure: 'сокровищница',
  trap: 'комната-ловушка',
  event: 'событие',
  rest: 'привал',
  merchant: 'торговец',
  teleport: 'портал',
  fork: 'развилка',
  deadend: 'тупик',
};
const TORCH_COST = 3;
const CHALLENGE_DOING: Record<string, string> = {
  lockpick: 'взламывает замок',
  shield: 'поднимает щит',
  gate: 'держит проход',
  seal: 'снимает печать',
  search: 'обыскивает комнату',
  scout: 'крадётся разведать путь',
  disarm: 'обезвреживает ловушку',
  insight: 'вчитывается в знаки',
  watch: 'встаёт в дозор',
  ...Object.fromEntries(Object.entries(SECRET_CRAFT).map(([k, v]) => [k, v.doing])),
};
/** The badge over a member's figurine while they play a minigame, by its kind. */
const CHALLENGE_ICON: Record<string, string> = {
  lockpick: '🗝️',
  mechanism: '⚙️',
  illusion: '👁️',
  rubble: '🪨',
  shield: '🛡️',
  gate: '🚪',
  seal: '✴️',
  search: '🔍',
  scout: '👣',
  disarm: '✂️',
  insight: '✨',
};
const busyOf = (kind: string): MemberBusy => {
  const doing = CHALLENGE_DOING[kind] ?? 'чем-то занят';
  return { icon: CHALLENGE_ICON[kind] ?? '⏳', text: doing.charAt(0).toUpperCase() + doing.slice(1) };
};

// --- Component ---

const DungeonSessionPage = () => {
  const { sessionId: sessionIdParam } = useParams<{ sessionId: string }>();
  const sessionId = Number(sessionIdParam) || null;
  const dispatch = useAppDispatch();
  const navigate = useNavigate();

  const storedState = useAppSelector(selectSessionState);
  const stateError = useAppSelector(selectSessionStateError);
  const stateLoading = useAppSelector(selectStateLoading);
  const moveLoading = useAppSelector(selectMoveLoading);
  const fleeLoading = useAppSelector(selectFleeLoading);
  const interactLoading = useAppSelector(selectInteractLoading);
  const lastMoveResponse = useAppSelector(selectLastMoveResponse);
  const lastFleeResponse = useAppSelector(selectLastFleeResponse);
  const lastFinalizeResponse = useAppSelector(selectLastFinalizeResponse);
  const skippedMembers = useAppSelector(selectLastSkippedMembers);
  const characterId = useAppSelector((state) => state.user.character?.id ?? null);

  // A state left over from another run must never be shown here.
  const session = storedState && storedState.session_id === sessionId ? storedState : null;
  // A refresh that failed once the run is on screen: say so (the page keeps showing the last state it had).
  const hasSession = !!session;
  useEffect(() => {
    if (hasSession && stateError) toast.error(stateError, { id: 'dungeon-state-error' });
  }, [hasSession, stateError]);

  const [showFleeModal, setShowFleeModal] = useState(false);
  const [showMoveBanner, setShowMoveBanner] = useState(false);
  const [mobileTab, setMobileTab] = useState<MobileTab>('map');
  // The run's chat and log (FEAT-176), lines not seen yet, and what each member just said (bubbles on the table).
  const [chatEntries, setChatEntries] = useState<ChatEntry[]>([]);
  const [chatUnread, setChatUnread] = useState(0);
  const chatVisible = useRef(false);
  const [speech, setSpeech] = useState<Map<number, { text: string; at: number }>>(new Map());
  // Who is in a minigame right now (FEAT-176): from the state, kept fresh by the challenge events.
  const [busyKinds, setBusyKinds] = useState<Map<number, string>>(new Map());
  const speak = useCallback((characterId: number, text: string) => {
    setSpeech((prev) => new Map(prev).set(characterId, { text, at: performance.now() }));
  }, []);
  const addChat = useCallback((entry: ChatEntry) => {
    setChatEntries((prev) => (prev.some((e) => e.id === entry.id) ? prev : [...prev, entry]));
  }, []);
  const [movingToRoomId, setMovingToRoomId] = useState<number | null>(null);
  const [squadMoveEvent, setSquadMoveEvent] = useState<BoardMoveEvent | null>(null);
  // Marks flashing over the table, and the one about to be made.
  const [pings, setPings] = useState<BoardMark[]>([]);
  const [markArmed, setMarkArmed] = useState<BoardPingKind | null>(null);
  const [voting, setVoting] = useState(false);

  const isLeader = useMemo(
    () => !!session && !!characterId && session.members.some((m) => m.character_id === characterId && m.is_leader),
    [session, characterId],
  );
  const isLeaderRef = useRef(isLeader);
  isLeaderRef.current = isLeader;
  const pawnColorsRef = useRef(new Map<number, string>());
  const characterIdRef = useRef(characterId);
  characterIdRef.current = characterId;

  // --- Loading the state ---

  const refresh = useCallback(() => {
    if (sessionId && characterId) {
      dispatch(fetchSessionState({ sessionId, characterId }));
    }
  }, [dispatch, sessionId, characterId]);

  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refreshSoon = useCallback(() => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(refresh, REFRESH_DEBOUNCE_MS);
  }, [refresh]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(
    () => () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
      dispatch(clearDungeonState());
    },
    [dispatch],
  );

  // Fallback for a missed battle result: the state endpoint polls the battle.
  const phase = session?.phase ?? null;
  useEffect(() => {
    if (phase !== 'in_battle') return;
    const timer = setInterval(refresh, BATTLE_POLL_MS);
    return () => clearInterval(timer);
  }, [phase, refresh]);

  // --- WebSocket ---

  const handleWsMessage = useCallback(
    (msg: DungeonWsMessage) => {
      const data = msg.data;
      const message = str(data.message);
      const quiet = isLeaderRef.current && LEADER_ECHO_EVENTS.has(msg.type);

      // A squadmate's mark: flash it on the table; nothing else has changed.
      if (msg.type === 'party_ping') {
        const roomId = typeof data.room_id === 'number' ? data.room_id : null;
        const kind = str(data.kind) as BoardPingKind | null;
        const from = typeof data.character_id === 'number' ? data.character_id : null;
        if (roomId === null || !kind || from === null) return;
        speak(from, markRemark(kind));
        const mark: BoardMark = {
          key: `ping-${from}-${performance.now()}`,
          roomId,
          kind,
          color: pawnColorsRef.current.get(from) ?? '#f0d95c',
          at: performance.now(),
        };
        setPings((prev) => [...prev, mark]);
        setTimeout(() => setPings((prev) => prev.filter((p) => p !== mark)), MARK_SECONDS * 1000);
        playDungeonSound('mark');
        return;
      }

      // A line in the chat: shown at once, said over the figurine, counted until the chat is looked at.
      if (msg.type === 'chat_message') {
        const entry = data as unknown as ChatEntry;
        if (!entry || typeof entry.id !== 'string') return;
        addChat(entry);
        if (entry.kind === 'say' && typeof entry.character_id === 'number') speak(entry.character_id, entry.text);
        if (!chatVisible.current && entry.character_id !== characterIdRef.current) setChatUnread((n) => n + 1);
        return;
      }

      switch (msg.type) {
        case 'party_vote': {
          // The voter says it aloud over their figurine.
          const by = typeof data.character_id === 'number' ? data.character_id : null;
          const votes = Array.isArray(data.votes) ? (data.votes as { character_id: number; corridor_id?: number | null; portal?: boolean }[]) : [];
          const vote = votes.find((v) => v.character_id === by);
          if (by !== null && vote) speak(by, voteRemark(vote));
          break;
        }
        case 'session_status': {
          const status = str(data.status);
          // Closing the run: the final screen already says so.
          if (data.finalized) {
            /* no toast */
          } else if (status === 'wiped') toast.error(message ?? 'Группа пала...', { duration: 8000 });
          else if (status === 'completed') toast.success(message ?? 'Подземелье пройдено!');
          else if (message) toast(message);
          // Locks change on every end of the run (banner, location page).
          if (status !== 'active' || data.finalized) dispatch(getMe());
          break;
        }
        case 'battle_started': {
          if (!quiet) {
            const names = Array.isArray(data.mob_names) ? (data.mob_names as string[]).join(', ') : '';
            toast(`${message ?? 'Бой начинается!'}${names ? ` Противники: ${names}` : ''}`, { icon: '⚔️' });
          }
          break;
        }
        case 'battle_ended': {
          if (data.party_won) toast.success(message ?? 'Победа!');
          else if (data.aborted) toast(message ?? 'Бой прерван.');
          else toast.error(message ?? 'Поражение...');
          break;
        }
        case 'member_status_changed': {
          const name = str(data.name) ?? 'Участник';
          const status = str(data.status) ?? str(data.new_status);
          if (status === 'dead') toast.error(`${name} пал(а) в бою`);
          else if (status === 'alive' && !quiet) toast.success(message ?? `${name} снова в строю`);
          break;
        }
        case 'loot_added': {
          if (!quiet) toast.success(`Получено: ${str(data.item_name) ?? 'ничего'}`);
          break;
        }
        case 'room_entered': {
          // A squadmate sees the leader's move played on the board too (the leader has his own response).
          if (!isLeaderRef.current && !data.teleported) {
            setSquadMoveEvent({
              corridor_event: obj<CorridorEvent>(data.corridor_event),
              room_event: obj<RoomEvent>(data.room_event),
              new_room_id: obj<{ id?: number }>(data.room)?.id ?? null,
              at: performance.now(),
            });
          }
          if (!quiet && message) toast(message);
          break;
        }
        case 'challenge_started': {
          const who = Number(data.character_id);
          const kind = str(data.kind);
          if (who && kind) {
            setBusyKinds((prev) => new Map(prev).set(who, kind));
            // A game left to lapse sends no word of its end: stop showing it when it would have run out.
            const lapse = Number(data.busy_ms);
            if (lapse > 0) {
              window.setTimeout(
                () =>
                  setBusyKinds((prev) => {
                    if (prev.get(who) !== kind) return prev;
                    const next = new Map(prev);
                    next.delete(who);
                    return next;
                  }),
                lapse,
              );
            }
          }
          if (data.character_id !== characterIdRef.current) {
            const doing = CHALLENGE_DOING[str(data.kind) ?? ''] ?? 'чем-то занят';
            toast(`${str(data.name) ?? 'Участник'} ${doing}…`, { icon: '🗝️' });
          }
          break;
        }
        case 'challenge_finished': {
          const who = Number(data.character_id);
          setBusyKinds((prev) => {
            if (!prev.has(who)) return prev;
            const next = new Map(prev);
            next.delete(who);
            return next;
          });
          // The one who played sees it in their own window.
          if (data.character_id !== characterIdRef.current && message) {
            if (data.passed) toast.success(message);
            else toast.error(message);
          }
          break;
        }
        case 'mana_core_revealed':
        case 'leader_changed':
          if (message) toast(message, { icon: msg.type === 'mana_core_revealed' ? '💎' : '👑' });
          break;
        default:
          if (!quiet && message) toast(message);
          break;
      }
      refreshSoon();
    },
    [dispatch, refreshSoon, speak, addChat],
  );

  const runOver = !session || session.phase === 'finished' || session.phase === 'wiped';
  const { connected, reconnecting, reconnect } = useDungeonWebSocket(
    !runOver ? sessionId : null,
    getAccessToken(),
    handleWsMessage,
  );

  // Back on the line after a drop: whatever was said meanwhile is lost, so read the run afresh.
  const everConnectedRef = useRef(false);
  useEffect(() => {
    if (!connected) return;
    if (everConnectedRef.current) refresh();
    everConnectedRef.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected]);
  // Gave up reconnecting (the run may have ended meanwhile): read it once more.
  useEffect(() => {
    if (!connected && !reconnecting && everConnectedRef.current) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected, reconnecting]);

  // --- Move banner ---

  // A battle started by the move that is no longer on (won, lost or broken off): its "go to battle" banner goes.
  const sessionPhase = session?.phase;
  const activeBattleId = session?.active_battle_id ?? null;
  useEffect(() => {
    if (!lastMoveResponse) return;
    const battleId = moveBattleId(lastMoveResponse);
    if (!battleId || sessionPhase === undefined) return;
    if (sessionPhase !== 'in_battle' || (activeBattleId !== null && activeBattleId !== battleId)) {
      setShowMoveBanner(false);
      dispatch(clearMoveResponse());
    }
  }, [lastMoveResponse, sessionPhase, activeBattleId, dispatch]);

  useEffect(() => {
    if (!lastMoveResponse) return;
    // Loads asked for before the move landed are thrown away (dungeonSlice): ask for the state after it.
    if (sessionId && characterId) dispatch(fetchSessionState({ sessionId, characterId }));
    setMovingToRoomId(null);
    const hasNews = moveHasNews(lastMoveResponse);
    setShowMoveBanner(hasNews);
    if (!hasNews) {
      dispatch(clearMoveResponse());
      return;
    }
    const startedBattle = !!moveBattleId(lastMoveResponse);
    if (startedBattle) return; // stays until the player goes to the battle
    const timer = setTimeout(() => {
      setShowMoveBanner(false);
      dispatch(clearMoveResponse());
    }, MOVE_BANNER_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastMoveResponse, dispatch]);

  useEffect(() => {
    if (!moveLoading) setMovingToRoomId(null);
  }, [moveLoading]);

  // --- Handlers ---

  const canMove =
    isLeader && !!session && (session.phase === 'exploring' || session.phase === 'battle_pending') && !moveLoading;
  // Everyone living has a say on the way on; only the leader leads (FEAT-176).
  const iAmAlive = !!session?.members.some((m) => m.character_id === characterId && m.status === 'alive');
  const myClassId = session?.members.find((m) => m.character_id === characterId)?.class_id;
  const iAmRogue = myClassId === ROGUE_CLASS_ID;
  const canChoose =
    iAmAlive && !!session && (session.phase === 'exploring' || session.phase === 'battle_pending') && !moveLoading;
  const waitingFor = session?.waiting_for ?? [];
  const waitingNames = (session?.members ?? [])
    .filter((m) => waitingFor.includes(m.character_id))
    .map((m) => m.name)
    .join(', ');

  const handleVote = useCallback(
    async (choice: { corridorId?: number; portal?: boolean }) => {
      if (!sessionId || !characterId) return;
      setVoting(true);
      try {
        await voteRoute(sessionId, characterId, choice);
        playDungeonSound('vote');
      } catch (err: unknown) {
        toast.error(getErrorMessage(err, 'Не удалось предложить путь'));
      } finally {
        setVoting(false);
        dispatch(fetchSessionState({ sessionId, characterId }));
      }
    },
    [sessionId, characterId, dispatch],
  );

  // The run's chat so far (then new lines come over the socket).
  useEffect(() => {
    if (!sessionId || !characterId) return;
    let cancelled = false;
    getChat(sessionId, characterId)
      .then((entries) => {
        if (cancelled) return;
        setChatEntries((prev) => {
          const known = new Set(entries.map((e) => e.id));
          return [...entries, ...prev.filter((e) => !known.has(e.id))];
        });
      })
      .catch((err: unknown) => {
        if (!cancelled) toast.error(getErrorMessage(err, 'Не удалось загрузить чат подземелья'));
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, characterId]);

  const handleSay = useCallback(
    async (text: string) => {
      if (!sessionId || !characterId) return false;
      try {
        const entry = await sayChat(sessionId, characterId, text);
        addChat(entry);
        speak(characterId, entry.text);
        return true;
      } catch (err: unknown) {
        toast.error(getErrorMessage(err, 'Не удалось отправить сообщение'));
        return false;
      }
    },
    [sessionId, characterId, addChat, speak],
  );

  // The chat in view (a tab): nothing unread while it is.
  const handleBoardTab = useCallback((tab: BoardTab | null) => {
    chatVisible.current = tab === 'chat';
    if (tab === 'chat') setChatUnread(0);
  }, []);

  const handlePing = useCallback(
    async (kind: BoardPingKind, roomId: number) => {
      if (!sessionId || !characterId) return;
      setMarkArmed(null);
      try {
        await pingBoard(sessionId, characterId, kind, roomId);
      } catch (err: unknown) {
        toast.error(getErrorMessage(err, 'Не удалось поставить метку'));
      }
    },
    [sessionId, characterId],
  );

  // A locked door without its key: what the party can do about it.
  const [lockedExit, setLockedExit] = useState<RoomExit | null>(null);
  const [pickingLock, setPickingLock] = useState(false);
  // A class challenge being played in its window.
  const [challenge, setChallenge] = useState<ChallengeStart | null>(null);

  const handleMapMove = useCallback(
    (corridorId: number) => {
      if (!sessionId || !characterId || !canMove) return;
      if (waitingFor.length > 0) {
        toast(`Отряд ещё решает, куда идти: ждём ${waitingNames}`, { icon: '⏳' });
        return;
      }
      const exit = session?.current_room?.exits.find((e) => e.corridor_id === corridorId);
      if (exit?.gate) {
        toast(`Путь преграждает ${GATE_NAMES[exit.gate].name} — сначала её нужно поднять и подпереть.`, { icon: '⛓️' });
        return;
      }
      if (exit?.sealed) {
        toast('Проход запечатан магической печатью — сначала её нужно снять.', { icon: '🔮' });
        return;
      }
      if (exit?.locked) {
        if (!exit.lock_key || !(session?.keys ?? []).includes(exit.lock_key)) {
          setLockedExit(exit);
          return;
        }
        // The key turns in the lock.
        playDungeonSound('disarm');
      }
      setLockedExit(null);
      setMovingToRoomId(exit ? exit.to_room_id : null);
      dispatch(moveDungeon({ sessionId, characterId, corridorId }));
    },
    [sessionId, characterId, canMove, session, dispatch, waitingFor.length, waitingNames],
  );

  /** A lock picked or not: the door's card goes once it is open; stamina has changed. */
  const afterChallenge = useCallback(
    (result: ChallengeResult) => {
      playDungeonSound(result.passed ? 'disarm' : 'trap');
      if (result.passed) setLockedExit(null);
      if (sessionId && characterId) dispatch(fetchSessionState({ sessionId, characterId }));
      dispatch(getMe());
    },
    [sessionId, characterId, dispatch],
  );

  /** Any living member takes on a challenge: the minigame, or a plain roll of their stat. */
  const handleChallenge = useCallback(
    async (kind: ChallengeKind, corridorId: number | null, mode: 'game' | 'roll') => {
      if (!sessionId || !characterId) return;
      setPickingLock(true);
      try {
        const started = await startChallenge(sessionId, characterId, kind, corridorId, mode);
        if (started.result) {
          if (started.result.passed) toast.success(started.result.message);
          else toast.error(started.result.message);
          afterChallenge(started.result);
        } else {
          setChallenge(started);
          dispatch(getMe());
        }
      } catch (err: unknown) {
        toast.error(getErrorMessage(err, 'Не удалось взяться за дело'));
      } finally {
        setPickingLock(false);
      }
    },
    [sessionId, characterId, afterChallenge, dispatch],
  );
  /** A light in a dark room: a mage's spell, anyone else's torch. */
  const [lighting, setLighting] = useState(false);
  const handleLight = useCallback(async () => {
    if (!sessionId || !characterId) return;
    setLighting(true);
    try {
      const lit = await lightRoom(sessionId, characterId);
      toast.success(lit.message);
      dispatch(fetchSessionState({ sessionId, characterId }));
      dispatch(getMe());
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, 'Не удалось зажечь свет'));
    } finally {
      setLighting(false);
    }
  }, [sessionId, characterId, dispatch]);

  const handlePickLock = useCallback(
    (mode: 'game' | 'roll') => {
      if (lockedExit) void handleChallenge('lockpick', lockedExit.corridor_id, mode);
    },
    [lockedExit, handleChallenge],
  );

  const handleChallengeStep = useCallback(
    async (move: { x?: number; y?: number; index?: number }) => {
      if (!sessionId || !characterId || !challenge?.challenge_id) return null;
      try {
        const answer = await stepChallenge(sessionId, characterId, challenge.challenge_id, move);
        if (answer.result) afterChallenge(answer.result);
        return answer;
      } catch (err: unknown) {
        toast.error(getErrorMessage(err, 'Не удалось сделать ход'));
        return null;
      }
    },
    [sessionId, characterId, challenge, afterChallenge],
  );

  const handleChallengeFinish = useCallback(
    async (presses: number[]): Promise<ChallengeResult | null> => {
      if (!sessionId || !characterId || !challenge?.challenge_id) return null;
      try {
        const result = await finishChallenge(sessionId, characterId, challenge.challenge_id, presses);
        afterChallenge(result);
        return result;
      } catch (err: unknown) {
        toast.error(getErrorMessage(err, 'Не удалось завершить испытание'));
        return null;
      }
    },
    [sessionId, characterId, challenge, afterChallenge],
  );

  const handleFlee = useCallback(() => {
    if (!sessionId || !characterId) return;
    setShowFleeModal(false);
    dispatch(fleeDungeonThunk({ sessionId, characterId }))
      .unwrap()
      .then(() => dispatch(getMe()))
      .catch(() => {
        // toast + state refresh in the thunk
      });
  }, [dispatch, sessionId, characterId]);

  const goToBattle = useCallback(
    (battleId: number | null | undefined) => {
      if (!session || !battleId) {
        toast.error('Бой ещё не найден — обновите состояние');
        refresh();
        return;
      }
      try {
        sessionStorage.setItem(
          DUNGEON_BATTLE_RETURN_KEY,
          JSON.stringify({ battleId, sessionId: session.session_id }),
        );
      } catch {
        // Private mode: the battle page falls back to my-session.
      }
      dispatch(clearMoveResponse());
      navigate(battlePath(session.location_id, battleId));
    },
    [session, navigate, dispatch, refresh],
  );

  const handleStartBattle = useCallback(() => {
    if (!sessionId || !characterId) return;
    dispatch(interactRoom({ sessionId, characterId, action: 'start_battle' }));
  }, [dispatch, sessionId, characterId]);

  const backToLocation = useCallback(() => {
    if (session) navigate(`/location/${session.location_id}`);
    else navigate(-1);
  }, [session, navigate]);

  // --- 3D board ---

  const prefs = useClientPrefs();
  const webgl = useMemo(() => isWebGLAvailable(), []);
  const view3D =
    webgl && (prefs.dungeonView === '3d' || (prefs.dungeonView === 'auto' && prefs.graphics !== 'low'));
  const toggleView = useCallback(() => setClientPrefs({ dungeonView: view3D ? '2d' : '3d' }), [view3D]);
  // The 2D page lays out a sidebar (desktop) or tabs (phone) — only one is mounted, so panels load once.
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  // The 2D page: the chat is in view on a desktop (the sidebar) or in its phone tab.
  useEffect(() => {
    if (!view3D) {
      chatVisible.current = mobileTab === 'chat' || window.matchMedia('(min-width: 1024px)').matches;
      if (chatVisible.current) setChatUnread(0);
    }
  }, [view3D, mobileTab]);

  // Everything seen during the run stays on the table, even when a later state leaves it out.
  const boardMemory = useRef(createBoardMemory());
  const board = useMemo(() => (session ? sessionToBoard(session, boardMemory.current) : null), [session]);
  const members = session?.members;
  const shieldHolder = session?.shield?.character_id ?? null;
  useEffect(() => {
    if (members) setBusyKinds(new Map(members.filter((m) => m.busy).map((m) => [m.character_id, m.busy!])));
  }, [members]);
  const busy = useMemo(() => new Map([...busyKinds].map(([id, kind]) => [id, busyOf(kind)])), [busyKinds]);
  const pawns = useMemo(
    () => (members ? membersToPawns(members, shieldHolder, speech, busy) : []),
    [members, shieldHolder, speech, busy],
  );
  // The room the figurines have walked into on the table; its news waits for them.
  const [arrivedRoomId, setArrivedRoomId] = useState<number | null>(null);
  const currentRoomId = session?.current_room?.id ?? null;
  // The locked-door card belongs to the room it was asked about.
  useEffect(() => setLockedExit(null), [currentRoomId]);
  useEffect(() => {
    // Safety net: if the table never says so (it failed to load), don't hold anything for long.
    const timer = setTimeout(() => setArrivedRoomId(currentRoomId), ARRIVAL_FALLBACK_MS);
    return () => clearTimeout(timer);
  }, [currentRoomId]);

  // What the party walked into sounds once it is there: a trap snapping or disarmed, a rune circle.
  const soundedMove = useRef<MoveResponse | null>(null);
  useEffect(() => {
    if (!lastMoveResponse || soundedMove.current === lastMoveResponse) return;
    if (arrivedRoomId === null || arrivedRoomId !== currentRoomId) return;
    soundedMove.current = lastMoveResponse;
    const ce = lastMoveResponse.corridor_event;
    let re: RoomEvent | null | undefined = lastMoveResponse.room_event;
    if (re?.type === 'teleported') {
      if (re.red_portal || re.fell) playDungeonSound('trap');
      if (!re.fell) playDungeonSound('teleport', re.red_portal ? 300 : 0);
    }
    while (re?.type === 'teleported') re = re.followup;
    const trap =
      re?.type === 'trap_triggered' || re?.type === 'portal_spotted' || re?.type === 'drop_spotted'
        ? re
        : ce?.type === 'trap'
          ? ce
          : null;
    if (trap && typeof trap.passed === 'boolean') playDungeonSound(trap.passed ? 'disarm' : 'trap');
  }, [lastMoveResponse, arrivedRoomId, currentRoomId]);

  // A frame wears its figurine's colour, so the two are easy to match.
  const pawnColors = useMemo(() => new Map(pawns.map((p) => [p.id, p.color])), [pawns]);
  pawnColorsRef.current = pawnColors;

  const leaderMoveEvent = useMemo<BoardMoveEvent | null>(
    () =>
      lastMoveResponse
        ? {
            corridor_event: lastMoveResponse.corridor_event,
            room_event: lastMoveResponse.room_event,
            new_room_id: lastMoveResponse.new_room?.id ?? null,
            at: performance.now(),
          }
        : null,
    [lastMoveResponse],
  );
  const boardEvent =
    leaderMoveEvent && (!squadMoveEvent || leaderMoveEvent.at > squadMoveEvent.at) ? leaderMoveEvent : squadMoveEvent;
  const shownBoard = useBoardPresentation(
    boardEvent,
    session?.current_room?.id ?? null,
    board?.revealed ?? NO_ROOMS,
    view3D,
  );

  // The party halfway down a corridor: a trapped stretch being shown, or an ambush being fought.
  const ambush = session?.ambush ?? null;
  const boardCorridor = useMemo<CorridorScene | null>(
    () =>
      shownBoard.corridor ??
      (ambush && shownBoard.roomId === ambush.from_room_id
        ? { from: ambush.from_room_id, to: ambush.to_room_id, ambush: true, trap: null }
        : null),
    [shownBoard.corridor, shownBoard.roomId, ambush],
  );

  // The rock under the table covers the shown floor's whole span from the start.
  const extents = session?.extents;
  const floorSpan = useMemo<FloorSpan | null>(() => {
    const e = extents?.find((x) => x.floor === (board ? (board.floorOf.get(shownBoard.roomId ?? -1) ?? board.floor) : 1));
    return e ? { minCol: e.min_col, maxCol: e.max_col, minRow: e.min_row, maxRow: e.max_row } : null;
  }, [extents, board, shownBoard.roomId]);

  // The table shows the floor of the room the figurines stand in (a fall is played step by step).
  const shownFloor = board ? (board.floorOf.get(shownBoard.roomId ?? -1) ?? board.floor) : 1;
  const shownDungeon = useMemo(
    () =>
      !board
        ? null
        : shownFloor === board.floor
          ? board.dungeon
          : boardOfFloor(
              boardMemory.current,
              board.dungeon.name,
              shownFloor,
              shownBoard.roomId,
              floorTheme(session?.theme, session?.floor_themes, shownFloor),
            ),
    [board, shownFloor, shownBoard.roomId, session?.theme, session?.floor_themes],
  );

  /** Rooms the leader can walk to now, with the corridor to take. */
  const boardExits = useMemo(() => {
    const exits = new Map<number, number>();
    const here = session?.current_room;
    if (!canChoose || !here) return exits;
    here.exits.forEach((exit) => {
      // Held up by enemies: only back into explored rooms.
      if (session?.phase === 'battle_pending' && !exit.explored) return;
      if (!exits.has(exit.to_room_id)) exits.set(exit.to_room_id, exit.corridor_id);
    });
    return exits;
  }, [canChoose, session]);
  const reachable = useMemo(
    () => (shownBoard.busy ? NO_ROOMS : new Set(boardExits.keys())),
    [boardExits, shownBoard.busy],
  );

  /** The card by the cursor on the table: what the party knows of a room, and the way there. */
  const describeRoom = useCallback(
    (roomId: number) => {
      if (!session || !board) return null;
      const exit = session.current_room?.exits.find((e) => e.to_room_id === roomId);
      const room = shownDungeon?.rooms.find((r) => r.id === roomId);
      if (!room && exit && exit.passage && exit.passage !== 'corridor') {
        // A way to another floor: stairs, a drop, a lift.
        const lines = [`Ведёт на этаж ${exit.to_floor ?? '?'}`];
        if (reachable.has(roomId)) lines.push(`Переход: ${exit.stamina_cost} выносливости`);
        if (exit.locked) lines.push(lockLine(exit, session.keys ?? []));
        return { title: passageTitle(exit, session.current_room?.floor), lines };
      }
      if (!room) return null;
      const lines: string[] = [];
      const known = board.revealed.has(roomId);
      if (!known) {
        if (session.stability_type === 'static') lines.push('Очертания известны по карте');
      } else {
        const kind =
          room.type === 'entrance'
            ? 'Вход'
            : room.portal
              ? room.portal === 'red'
                ? 'Красный портал'
                : 'Синий портал'
              : ROOM_TYPE_LABELS[room.type] ?? '';
        if (kind && kind !== room.name) lines.push(kind);
        if (board.cleared.has(roomId)) lines.push(SPENT_LABELS[room.type] ?? 'Зачищена');
        else if ((room.enemies ?? 0) > 0) lines.push(`Враги: ${room.enemies}`);
      }
      if (roomId === session.current_room?.id) lines.push('Группа здесь');
      else if (exit && reachable.has(roomId)) lines.push(`Переход: ${exit.stamina_cost} выносливости`);
      if (exit?.locked) lines.push(lockLine(exit, session.keys ?? []));
      return { title: known ? room.name : 'Неизведанная комната', lines };
    },
    [board, shownDungeon, session, reachable],
  );

  const handleBoardClick = useCallback(
    (roomId: number) => {
      if (markArmed) {
        void handlePing(markArmed, roomId);
        return;
      }
      const corridorId = boardExits.get(roomId);
      if (corridorId === undefined || shownBoard.busy) return;
      if (isLeader) {
        handleMapMove(corridorId);
        return;
      }
      const exit = session?.current_room?.exits.find((e) => e.corridor_id === corridorId);
      if (exit?.locked && (!exit.lock_key || !(session?.keys ?? []).includes(exit.lock_key))) setLockedExit(exit);
      void handleVote({ corridorId });
    },
    [boardExits, shownBoard.busy, handleMapMove, handleVote, handlePing, markArmed, isLeader, session],
  );

  /** The members' flags on the rooms they would go to, and the marks flashing now. */
  const boardMarks = useMemo<BoardMark[]>(() => {
    const exits = session?.current_room?.exits ?? [];
    const flags: BoardMark[] = [];
    (session?.votes ?? []).forEach((v) => {
      const roomId = v.portal
        ? session?.current_room?.id
        : exits.find((e) => e.corridor_id === v.corridor_id)?.to_room_id;
      if (roomId === undefined || (!v.portal && !v.corridor_id)) return;
      flags.push({
        key: `vote-${v.character_id}`,
        roomId,
        kind: 'vote',
        color: pawnColors.get(v.character_id) ?? '#f0d95c',
      });
    });
    return [...flags, ...pings];
  }, [session, pawnColors, pings]);

  // --- Loading / error ---

  if (!session) {
    if (stateError && !stateLoading) {
      return (
        <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4 text-center px-2">
          <p className="text-site-red text-base">{stateError}</p>
          <div className="flex flex-col sm:flex-row gap-3">
            <button onClick={refresh} className="btn-blue text-sm px-6 py-2">Повторить</button>
            <button onClick={() => navigate(-1)} className="btn-line text-sm px-6 py-2">Назад</button>
          </div>
        </div>
      );
    }
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-10 h-10 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

  // Phases with the map: the table can stand in for it.
  const mapPhase = MAP_PHASES.has(session.phase);
  const boardShown = view3D && mapPhase && !!board && shownBoard.roomId !== null;

  const header = (
    <SessionHeader
      session={session}
      connected={connected}
      reconnecting={reconnecting}
      onReconnect={reconnect}
      onBack={backToLocation}
      compact={boardShown}
      viewToggle={
        webgl && mapPhase ? (
          <button
            type="button"
            onClick={toggleView}
            className="text-xs px-3 py-1 rounded-card border border-white/15 text-white/80 hover:text-site-blue hover:border-site-blue/50 transition-colors duration-200 ease-site whitespace-nowrap"
          >
            {view3D ? '2D-карта' : '3D-стол'}
          </button>
        ) : null
      }
    />
  );

  /** The run on the table, with the page's panels over it. */
  const chatPanel = (
    <DungeonChat
      entries={chatEntries}
      colors={pawnColors}
      currentCharacterId={characterId}
      onSay={handleSay}
      canWrite={session.status === 'active'}
      fill
    />
  );

  const renderBoard = ({
    banners,
    roomPanel,
    roomActions = null,
    roomTitle,
    groupPanel,
    decision = null,
    roomHasAction = false,
  }: {
    banners: ReactNode;
    roomPanel: ReactNode;
    roomActions?: ReactNode;
    roomTitle: string;
    groupPanel: ReactNode;
    decision?: ReactNode;
    roomHasAction?: boolean;
  }) =>
    board && shownDungeon && shownBoard.roomId !== null ? (
      <DungeonBoardView
        dungeon={shownDungeon}
        floor={shownFloor}
        party={pawns}
        currentRoomId={shownBoard.roomId}
        revealed={shownBoard.revealed}
        cleared={board.cleared}
        reachable={reachable}
        dice={shownBoard.dice}
        corridor={boardCorridor}
        span={floorSpan}
        lowGraphics={prefs.graphics === 'low'}
        stability={session.stability_type}
        onPartyArrived={setArrivedRoomId}
        onTileClick={handleBoardClick}
        header={header}
        banners={banners}
        roomPanel={roomPanel}
        roomActions={roomActions}
        roomTitle={roomTitle}
        groupPanel={groupPanel}
        chatPanel={chatPanel}
        chatUnread={chatUnread}
        onTabChange={handleBoardTab}
        decision={decision}
        roomHasAction={roomHasAction}
        describeRoom={describeRoom}
        partyStrip={
          <PartyFrames members={session.members} currentCharacterId={characterId} colors={pawnColors} busy={busy} compact />
        }
        marks={boardMarks}
        markTools={session.members.length > 1 ? <MarkTools armed={markArmed} onArm={setMarkArmed} /> : null}
      />
    ) : null;

  const skippedNotice = skippedMembers.length > 0 && (
    <SkippedMembersNotice members={skippedMembers} onClose={() => dispatch(clearSkippedMembers())} />
  );

  // --- Wipe ---
  if (session.phase === 'wiped') {
    return (
      <div className="flex flex-col gap-4 sm:gap-6 pb-10">
        {header}
        <WipeScreen session={session} onBack={backToLocation} />
      </div>
    );
  }

  // --- Closed run ---
  if (session.phase === 'finished') {
    return (
      <div className="flex flex-col gap-4 sm:gap-6 pb-10">
        {header}
        <FinishedScreen
          session={session}
          finalize={lastFinalizeResponse}
          flee={lastFleeResponse}
          onBack={backToLocation}
        />
      </div>
    );
  }

  // --- Loot sharing (completed or escaped) ---
  if (session.phase === 'distributing_loot') {
    return (
      <div className="flex flex-col gap-4 sm:gap-6 pb-10">
        {header}
        <RunEndedNotice session={session} flee={lastFleeResponse} onBack={backToLocation} />
        <DungeonLootDistribution
          sessionId={session.session_id}
          characterId={characterId ?? 0}
          groupInventory={session.group_inventory}
          members={session.members}
          isLeader={isLeader}
        />
        <DungeonPartyPanel members={session.members} currentCharacterId={characterId} busy={busy} />
      </div>
    );
  }

  // --- Battle in progress ---
  if (session.phase === 'in_battle') {
    if (boardShown) {
      const onTheWay = arrivedRoomId !== session.current_room?.id;
      const battleCard = onTheWay ? (
        <p className="text-white/70 text-xs bg-black/60 backdrop-blur-sm rounded-card px-3 py-2">Группа в пути...</p>
      ) : (
        <div className="bg-black/60 rounded-card p-4 backdrop-blur-sm flex flex-col gap-3 border border-site-red/40">
          <div>
            <h2 className="gold-text text-lg font-medium uppercase mb-1">Идёт бой!</h2>
            <p className="text-white/60 text-sm">
              Группа сражается{session.current_room ? ` у комнаты «${session.current_room.name}»` : ''}.
              После боя вы вернётесь сюда.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => goToBattle(session.active_battle_id)}
              disabled={!session.active_battle_id}
              className="btn-blue text-sm px-5 py-2 whitespace-nowrap disabled:opacity-50"
            >
              Перейти к бою
            </button>
            <button onClick={refresh} disabled={stateLoading} className="btn-line text-sm px-4 py-2 disabled:opacity-50">
              {stateLoading ? 'Обновляем...' : 'Обновить'}
            </button>
          </div>
        </div>
      );
      // Same shape as the exploring branch below (fragment: board, modal slot),
      // so React keeps the board — and its WebGL context — across the battle.
      return (
        <>
          {renderBoard({
            banners: (
              <>
                {skippedNotice}
                {battleCard}
              </>
            ),
            roomPanel: (
              <div className="bg-black/40 rounded-card p-4 backdrop-blur-sm text-white/60 text-sm">
                Пока идёт бой, действия в комнате недоступны.
              </div>
            ),
            roomTitle: session.current_room?.name ?? 'бой',
            groupPanel: <DungeonInventory items={session.group_inventory} keys={session.keys} />,
          })}
          {null}
        </>
      );
    }
    return (
      <div className="flex flex-col gap-4 sm:gap-6 pb-10">
        {header}
        {skippedNotice}
        <div className="bg-black/60 rounded-card p-6 sm:p-8 backdrop-blur-sm flex flex-col items-center gap-5 text-center">
          <div className="text-4xl" aria-hidden>⚔️</div>
          <div>
            <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase mb-2">Идёт бой!</h2>
            <p className="text-white/60 text-sm">
              Группа сражается{session.current_room ? ` у комнаты «${session.current_room.name}»` : ''}.
              После боя вы вернётесь сюда.
            </p>
          </div>
          <div className="flex flex-col sm:flex-row gap-3 w-full sm:w-auto">
            <button
              onClick={() => goToBattle(session.active_battle_id)}
              disabled={!session.active_battle_id}
              className="btn-blue text-sm sm:text-base px-8 py-3 whitespace-nowrap disabled:opacity-50"
            >
              Перейти к бою
            </button>
            <button onClick={refresh} disabled={stateLoading} className="btn-line text-sm px-6 py-3 disabled:opacity-50">
              {stateLoading ? 'Обновляем...' : 'Обновить'}
            </button>
          </div>
        </div>
        <DungeonPartyPanel members={session.members} currentCharacterId={characterId} busy={busy} />
      </div>
    );
  }

  // --- Exploring / resting / battle pending ---
  const room = session.current_room;
  // On the table the room's news waits until the figurines have walked in.
  const partyArrived = !boardShown || (!!room && arrivedRoomId === room.id);
  const roomHasAction =
    !!room && partyArrived && !shownBoard.busy && shownBoard.roomId === room.id && roomNeedsAction(room, session);
  const roomPanel = !partyArrived ? (
    <div className="bg-black/40 rounded-card p-4 backdrop-blur-sm text-white/60 text-sm">Группа в пути...</div>
  ) : room ? (
    <DungeonRoom
      room={room}
      session={session}
      characterId={characterId ?? 0}
      isLeader={isLeader}
      onGoToBattle={() => goToBattle(session.active_battle_id)}
    />
  ) : (
    <div className="bg-black/40 rounded-card p-4 text-white/50 text-sm">Комната не определена</div>
  );

  const fleeButton = isLeader && (
    <button
      onClick={() => setShowFleeModal(true)}
      disabled={fleeLoading}
      className="text-sm px-4 py-2 rounded-card border border-site-red/40 text-site-red hover:bg-site-red/10 transition-colors disabled:opacity-50"
    >
      {fleeLoading ? 'Побег...' : 'Сбежать из подземелья'}
    </button>
  );

  const map = (
    <DungeonMap
      sessionState={session}
      stabilityType={session.stability_type ?? 'static'}
      onMoveToRoom={isLeader ? handleMapMove : (corridorId: number) => void handleVote({ corridorId })}
      isMoving={moveLoading}
      movingToRoomId={movingToRoomId}
      canMove={canChoose}
    />
  );

  const battlePendingBanner = session.phase === 'battle_pending' && partyArrived && (
    <div className="rounded-card border border-site-red/40 bg-site-bg backdrop-blur-sm p-3 sm:p-4 flex flex-col sm:flex-row sm:items-center gap-3">
      <p className="text-white text-sm flex-1">
        Путь преграждают враги. Начните бой или отступите в уже исследованную комнату.
      </p>
      {isLeader && (
        <button
          onClick={handleStartBattle}
          disabled={interactLoading}
          className="btn-blue text-sm px-5 py-2 self-start sm:self-auto disabled:opacity-50"
        >
          {interactLoading ? 'Начинаем...' : 'Начать бой'}
        </button>
      )}
    </div>
  );

  const lockedKey = lockedExit ? keyInfo(lockedExit.lock_key) : null;
  const lockBanner = lockedExit && lockedKey && (
    <div className="rounded-card border border-white/15 bg-site-bg backdrop-blur-sm p-3 sm:p-4 flex flex-col gap-3">
      <div className="flex items-start gap-3">
        <KeyGlyph color={lockedKey.color} className="w-6 h-6 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="text-white text-sm font-medium">Дверь заперта</p>
          <p className="text-white/60 text-xs mt-0.5">
            {lockedExit.lock_key
              ? `Нужен ${lockedKey.name.toLowerCase()}${lockedExit.lock_lever ? ' или рычаг где-то в подземелье' : ''}.`
              : 'Её открывает рычаг где-то в подземелье.'}{' '}
            {lockedExit.lock_pickable
              ? 'Взломать может любой из отряда: мини-игра или бросок ловкости. Выносливость тратит тот, кто взламывает.'
              : lockedExit.lock_key
                ? 'Этот замок не взломать.'
                : ''}
          </p>
        </div>
        <button
          onClick={() => setLockedExit(null)}
          className="text-white/40 hover:text-white text-lg leading-none shrink-0"
          aria-label="Закрыть"
        >
          ×
        </button>
      </div>
      {iAmAlive && lockedExit.lock_pickable && (
        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => void handlePickLock('game')}
              disabled={pickingLock}
              className="btn-blue text-sm px-5 py-2 disabled:opacity-50"
            >
              {pickingLock ? 'Берёмся...' : 'Взломать'}
            </button>
            <button
              onClick={() => void handlePickLock('roll')}
              disabled={pickingLock}
              className="btn-line text-sm px-4 py-2 disabled:opacity-50"
            >
              Бросок ловкости
            </button>
          </div>
          <p className="text-white/50 text-xs">
            {iAmRogue ? 'Замки — ваше ремесло.' : 'Вы не плут — замок поддастся хуже.'}
          </p>
        </div>
      )}
    </div>
  );

  const secrets = partyArrived && session.phase === 'exploring' ? room?.secrets ?? [] : [];
  const secretsCard = secrets.length > 0 && (
    <div className="rounded-card border border-[#b07aff]/30 bg-site-bg backdrop-blur-sm p-3 sm:p-4 flex flex-col gap-3">
      <p className="gold-text text-sm font-medium uppercase">Здесь что-то скрыто</p>
      {secrets.map((secret) => {
        const craft = SECRET_CRAFT[secret.kind];
        const mine = myClassId === craft.classId;
        return (
          <div key={secret.corridor_id} className="flex flex-col gap-2">
            <p className="text-white/80 text-sm italic">{secret.hint}</p>
            {iAmAlive && (
              <>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => void handleChallenge(secret.kind, secret.corridor_id, 'game')}
                    disabled={pickingLock}
                    className="btn-blue text-sm px-5 py-2 disabled:opacity-50"
                  >
                    {craft.action}
                  </button>
                  <button
                    onClick={() => void handleChallenge(secret.kind, secret.corridor_id, 'roll')}
                    disabled={pickingLock}
                    className="btn-line text-sm px-4 py-2 disabled:opacity-50"
                  >
                    Бросок {craft.stat}
                  </button>
                </div>
                <p className="text-white/50 text-xs">
                  {mine ? 'Это ваше ремесло.' : `Это ремесло ${craft.craft} — вам будет тяжелее.`}
                </p>
              </>
            )}
          </div>
        );
      })}
    </div>
  );

  // The warrior's own: the party shield for the next way out, gates down across the exits.
  const strengthShown = partyArrived && session.phase === 'exploring';
  const gates = strengthShown ? (room?.exits ?? []).filter((e) => e.gate) : [];
  const shield = session.shield ?? null;
  const shieldName = shield ? session.members.find((m) => m.character_id === shield.character_id)?.name ?? 'Участник' : null;
  const iAmWarrior = myClassId === WARRIOR_CLASS_ID;
  const strengthNote = (
    <p className="text-white/50 text-xs">{iAmWarrior ? 'Это ваше ремесло.' : 'Это ремесло воина — вам будет тяжелее.'}</p>
  );
  const strengthButtons = (kind: ChallengeKind, corridorId: number | null, action: string) => (
    <div className="flex flex-wrap gap-2">
      <button
        onClick={() => void handleChallenge(kind, corridorId, 'game')}
        disabled={pickingLock}
        className="btn-blue text-sm px-5 py-2 disabled:opacity-50"
      >
        {action}
      </button>
      <button
        onClick={() => void handleChallenge(kind, corridorId, 'roll')}
        disabled={pickingLock}
        className="btn-line text-sm px-4 py-2 disabled:opacity-50"
      >
        Бросок силы
      </button>
    </div>
  );
  const strengthCard = strengthShown && (
    <div className="rounded-card border border-white/15 bg-site-bg backdrop-blur-sm p-3 sm:p-4 flex flex-col gap-3">
      {gates.map((exit) => {
        const gate = GATE_NAMES[exit.gate as GateLook];
        return (
          <div key={exit.corridor_id} className="flex flex-col gap-2">
            <p className="text-white text-sm">
              Путь {exit.explored ? `в «${exit.to_room_name}»` : 'дальше'} преграждает {gate.name}.
            </p>
            <p className="text-white/60 text-xs">
              Её надо поднять и подпереть, тогда проход останется открытым. Сорвётся — ударит того, кто держал.
            </p>
            {iAmAlive && (
              <>
                {strengthButtons('gate', exit.corridor_id, `Поднять ${gate.acc}`)}
                {strengthNote}
              </>
            )}
          </div>
        );
      })}
      {gates.length > 0 && <div className="border-t border-white/10" />}
      <div className="flex flex-col gap-2">
        <p className="gold-text text-sm font-medium uppercase">Щит отряда</p>
        {shield ? (
          <p className="text-white/80 text-sm">
            Щит держит {shieldName}: ловушку или первый удар засады на следующем переходе примет на себя, и удар будет
            слабее на {Math.round(SHIELD_ABSORB * shield.block * 100)}%.
          </p>
        ) : (
          <>
            <p className="text-white/60 text-xs">
              Не поднят. Поднятый щит примет на себя ловушку или первый удар засады на следующем переходе — остальных не
              заденет.
            </p>
            {iAmAlive && (
              <>
                {strengthButtons('shield', null, 'Поднять щит')}
                {strengthNote}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );

  // The mage's and the rogue's: seals across the exits, a dark room, a room to search; the watch at a rest.
  const seals = strengthShown ? (room?.exits ?? []).filter((e) => e.sealed) : [];
  const iAmMage = myClassId === MAGE_CLASS_ID;
  const darkHere = strengthShown && !!room?.dark;
  const searchable = strengthShown && !!room && !room.searched && !room.dark;
  const watching = partyArrived && session.phase === 'resting' && room?.room_type === 'rest';
  // Looking ahead (FEAT-176): ways out to scout or with a found trap to disarm; an event or a portal to read.
  const scoutable = strengthShown && !room?.dark ? (room?.exits ?? []).filter((e) => !e.gate && !e.sealed && !e.locked) : [];
  const roomCfg = room?.room_config_visible as Record<string, unknown> | null | undefined;
  const readable =
    strengthShown &&
    !!room &&
    ((room.room_type === 'event' && roomCfg?.choice_made == null && !roomCfg?.choice_hints) ||
      (room.room_type === 'teleport' && roomCfg?.portal !== 'red' && !roomCfg?.portal_to));
  const watchName = room?.watch
    ? session.members.find((m) => m.character_id === room.watch?.character_id)?.name ?? 'Участник'
    : null;
  const craftNote = (classId: number, craft: string) => (
    <p className="text-white/50 text-xs">
      {myClassId === classId ? 'Это ваше ремесло.' : `Это ремесло ${craft} — вам будет тяжелее.`}
    </p>
  );
  const craftButtons = (kind: ChallengeKind, corridorId: number | null, action: string, roll: string) => (
    <div className="flex flex-wrap gap-2">
      <button
        onClick={() => void handleChallenge(kind, corridorId, 'game')}
        disabled={pickingLock}
        className="btn-blue text-sm px-5 py-2 disabled:opacity-50"
      >
        {action}
      </button>
      <button
        onClick={() => void handleChallenge(kind, corridorId, 'roll')}
        disabled={pickingLock}
        className="btn-line text-sm px-4 py-2 disabled:opacity-50"
      >
        {roll}
      </button>
    </div>
  );
  const scoutLine = (exit: (typeof scoutable)[number]) => {
    const s = exit.scout;
    if (!s) return null;
    const parts = [ROOM_KIND_NAMES[s.room_type] ?? 'комната'];
    if (s.mob_count) parts.push(`врагов: ${s.mob_count}`);
    if (s.trap) parts.push(s.disarmed ? 'ловушка обезврежена' : 'в коридоре ловушка');
    if (s.ambush) parts.push('возможна засада');
    return parts.join(' · ');
  };
  const craftCard = (seals.length > 0 || darkHere || searchable || watching || scoutable.length > 0 || readable) && (
    <div className="rounded-card border border-white/15 bg-site-bg backdrop-blur-sm p-3 sm:p-4 flex flex-col gap-3">
      {darkHere && (
        <div className="flex flex-col gap-2">
          <p className="gold-text text-sm font-medium uppercase">Здесь темно</p>
          <p className="text-white/60 text-xs">
            Не разобрать, куда ведут проходы, ловушки бьют больнее, а обыскивать в темноте бесполезно.
          </p>
          {iAmAlive && (
            <>
              <button
                onClick={() => void handleLight()}
                disabled={lighting}
                className="btn-blue text-sm px-5 py-2 self-start disabled:opacity-50"
              >
                {iAmMage
                  ? `Заклинание света (−${LIGHT_SPELL_COST} выносл.)`
                  : `Зажечь факел (−${TORCH_COST} выносл.)`}
              </button>
              <p className="text-white/50 text-xs">
                {iAmMage
                  ? 'Магический свет останется здесь до конца забега.'
                  : 'Факел горит, пока отряд здесь. Магический свет мага дешевле и держится весь забег.'}
              </p>
            </>
          )}
        </div>
      )}
      {seals.map((exit) => (
        <div key={exit.corridor_id} className="flex flex-col gap-2">
          <p className="text-white text-sm">
            Путь {exit.explored ? `в «${exit.to_room_name}»` : 'дальше'} закрыт магической печатью.
          </p>
          <p className="text-white/60 text-xs">Сорвётся — печать ударит того, кто её снимал.</p>
          {iAmAlive && (
            <>
              {craftButtons('seal', exit.corridor_id, 'Снять печать', 'Бросок интеллекта')}
              {craftNote(MAGE_CLASS_ID, 'мага')}
            </>
          )}
        </div>
      ))}
      {scoutable.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="gold-text text-sm font-medium uppercase">Разведка</p>
          {scoutable.map((exit) => (
            <div key={exit.corridor_id} className="flex flex-col gap-1.5 border-l-2 border-white/10 pl-2">
              <p className="text-white/80 text-sm">
                Путь {exit.explored ? `в «${exit.to_room_name}»` : 'в неизвестность'}
                {exit.scout && <span className="text-white/60 text-xs"> — {scoutLine(exit)}</span>}
              </p>
              {iAmAlive && !exit.scout && craftButtons('scout', exit.corridor_id, 'Разведать', 'Бросок ловкости')}
              {iAmAlive &&
                exit.scout?.trap &&
                !exit.scout.disarmed &&
                craftButtons('disarm', exit.corridor_id, 'Обезвредить ловушку', 'Бросок ловкости')}
            </div>
          ))}
          {iAmAlive && craftNote(ROGUE_CLASS_ID, 'плута')}
        </div>
      )}
      {readable && (
        <div className="flex flex-col gap-2">
          <p className="gold-text text-sm font-medium uppercase">Распознать</p>
          <p className="text-white/60 text-xs">
            {room?.room_type === 'event'
              ? 'Прочитать знаки события — станет видно, к чему ведёт каждый выбор.'
              : 'Вглядеться в портал — станет видно, куда он ведёт.'}
          </p>
          {iAmAlive && (
            <>
              {craftButtons('insight', null, 'Распознать', 'Бросок интеллекта')}
              {craftNote(MAGE_CLASS_ID, 'мага')}
            </>
          )}
        </div>
      )}
      {searchable && (
        <div className="flex flex-col gap-2">
          <p className="gold-text text-sm font-medium uppercase">Обыскать комнату</p>
          <p className="text-white/60 text-xs">Вдруг здесь что-то припрятано. Обыскать комнату можно только раз.</p>
          {iAmAlive && (
            <>
              {craftButtons('search', null, 'Обыскать', 'Бросок ловкости')}
              {craftNote(ROGUE_CLASS_ID, 'плута')}
            </>
          )}
        </div>
      )}
      {watching && (
        <div className="flex flex-col gap-2">
          <p className="gold-text text-sm font-medium uppercase">Дозор</p>
          {room?.watch ? (
            <p className="text-white/80 text-sm">
              В дозоре {watchName}
              {room.watch.passed ? ' — не сомкнёт глаз.' : ', но то и дело клюёт носом.'}
            </p>
          ) : (
            <>
              <p className="text-white/60 text-xs">
                Ночью к привалу могут подкрасться твари. Дозорный вовремя поднимет тревогу — без него отдых сорвётся.
              </p>
              {iAmAlive && (
                <>
                  <button
                    onClick={() => void handleChallenge('watch', null, 'roll')}
                    disabled={pickingLock}
                    className="btn-blue text-sm px-5 py-2 self-start disabled:opacity-50"
                  >
                    Встать в дозор (бросок силы)
                  </button>
                  {craftNote(WARRIOR_CLASS_ID, 'воина')}
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );

  const restingNote = session.phase === 'resting' && (
    <p className={`text-green-300/80 text-sm ${boardShown ? 'bg-black/60 backdrop-blur-sm rounded-card px-3 py-2' : ''}`}>
      Группа на привале — идти дальше можно после отдыха.
    </p>
  );

  const moveBanner = (
    <AnimatePresence>
      {showMoveBanner && lastMoveResponse && !shownBoard.busy && partyArrived && (
        <MoveEventBanner
          move={lastMoveResponse}
          onClose={() => {
            setShowMoveBanner(false);
            dispatch(clearMoveResponse());
          }}
          onGoToBattle={() => goToBattle(moveBattleId(lastMoveResponse))}
        />
      )}
    </AnimatePresence>
  );

  const leaderNote = !isLeader && session.members.length < 2 && (
    <p className={`text-white/40 text-xs ${boardShown ? 'bg-black/60 backdrop-blur-sm rounded-card px-3 py-2' : ''}`}>
      Группу ведёт лидер: он выбирает путь и действия в комнатах.
    </p>
  );

  const portalHere =
    room?.room_type === 'teleport' && room.room_config_visible?.portal !== 'red';
  const decision = partyArrived &&
    (session.phase === 'exploring' || session.phase === 'battle_pending') && (
      <PartyDecision
        session={session}
        characterId={characterId}
        isLeader={isLeader}
        colors={pawnColors}
        portalHere={portalHere}
        voting={voting}
        onVote={(choice) => void handleVote(choice)}
        overBoard={boardShown}
      />
    );

  const fleeModal = (
    <ModalShell
      open={showFleeModal}
      onClose={() => setShowFleeModal(false)}
      title="Сбежать из подземелья?"
      size="sm"
      footer={
        <>
          <button onClick={() => setShowFleeModal(false)} className="btn-line text-sm w-full sm:w-auto">
            Остаться
          </button>
          <button
            onClick={handleFlee}
            disabled={fleeLoading}
            className="text-sm px-5 py-2 w-full sm:w-auto rounded-card bg-site-red/20 border border-site-red/40 text-site-red hover:bg-site-red/30 transition-colors disabled:opacity-50"
          >
            {fleeLoading ? 'Побег...' : 'Сбежать'}
          </button>
        </>
      }
    >
      <p className="text-white/70 text-sm mb-2">
        Группа покинет подземелье. Отката не будет — подземелье сразу освободится.
      </p>
      <div className="bg-site-red/10 border border-site-red/30 rounded-card p-3">
        <p className="text-site-red text-sm font-medium">
          Каждая стопка добычи в общем инвентаре потеряется с шансом 50%.
        </p>
      </div>
      {session.group_inventory.length > 0 && (
        <div className="mt-4">
          <p className="text-white/50 text-xs mb-1">Под угрозой:</p>
          <div className="text-white/40 text-xs flex flex-wrap gap-x-3">
            {session.group_inventory.map((item, i) => (
              <span key={i}>{itemLabel(item)} ×{item.quantity}</span>
            ))}
          </div>
        </div>
      )}
    </ModalShell>
  );

  if (boardShown) {
    const movingNote = (moveLoading || !partyArrived) && (
      <p className="text-white/70 text-xs bg-black/60 backdrop-blur-sm rounded-card px-3 py-2">Группа в пути...</p>
    );
    return (
      <>
        {renderBoard({
          banners: (
            <>
              {skippedNotice}
              {battlePendingBanner}
              {restingNote}
              {movingNote}
              {moveBanner}
              {leaderNote}
            </>
          ),
          roomPanel,
          roomActions:
            lockBanner || secretsCard || strengthCard || craftCard ? (
              <>
                {lockBanner}
                {secretsCard}
                {strengthCard}
                {craftCard}
              </>
            ) : null,
          roomTitle: room?.name ?? '—',
          groupPanel: (
            <>
              <DungeonInventory items={session.group_inventory} keys={session.keys} />
              {fleeButton}
            </>
          ),
          decision,
          roomHasAction,
        })}
        {fleeModal}
        <ChallengeModal
          challenge={challenge}
          onFinish={handleChallengeFinish}
          onStep={handleChallengeStep}
          onClose={() => setChallenge(null)}
          use3D={view3D}
        />
      </>
    );
  }

  return (
    <div className="flex flex-col gap-4 sm:gap-6 pb-10">
      {header}
      {skippedNotice}
      {battlePendingBanner}
      {lockBanner}
      {secretsCard}
      {strengthCard}
      {craftCard}
      {restingNote}
      {moveBanner}
      {decision}

      {/* Mobile tab bar */}
      <div className="flex lg:hidden bg-black/40 rounded-card p-1 backdrop-blur-sm">
        {(['map', 'room', 'party', 'chat'] as MobileTab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setMobileTab(tab)}
            className={`flex-1 py-2 text-xs sm:text-sm font-medium rounded-card transition-colors ${
              mobileTab === tab ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/60'
            }`}
          >
            {tab === 'map' && 'Карта'}
            {tab === 'room' && 'Комната'}
            {tab === 'party' && 'Группа'}
            {tab === 'chat' && (
              <>
                Чат
                {chatUnread > 0 && (
                  <span className="ml-1 inline-flex min-w-[16px] h-4 px-1 items-center justify-center rounded-full bg-site-blue text-[10px] text-white">
                    {chatUnread}
                  </span>
                )}
              </>
            )}
          </button>
        ))}
      </div>

      {/* Desktop: map + sidebar */}
      {isDesktop && (
      <div className="flex gap-4">
        <div className="flex-1 min-w-0">{map}</div>
        <div className="w-80 shrink-0 flex flex-col gap-4">
          {roomPanel}
          <DungeonPartyPanel members={session.members} currentCharacterId={characterId} busy={busy} />
          <DungeonInventory items={session.group_inventory} keys={session.keys} compact />
          {fleeButton}
          <div className="gray-bg rounded-card p-3">
            <DungeonChat
              entries={chatEntries}
              colors={pawnColors}
              currentCharacterId={characterId}
              onSay={handleSay}
              canWrite={session.status === 'active'}
            />
          </div>
        </div>
      </div>

      )}

      {/* Mobile: tabs */}
      {!isDesktop && (
      <div>
        {mobileTab === 'map' && map}
        {mobileTab === 'room' && roomPanel}
        {mobileTab === 'party' && (
          <div className="flex flex-col gap-4">
            <DungeonPartyPanel members={session.members} currentCharacterId={characterId} busy={busy} />
            <DungeonInventory items={session.group_inventory} keys={session.keys} />
            {fleeButton}
          </div>
        )}
        {mobileTab === 'chat' && (
          <div className="gray-bg rounded-card p-3">
            <DungeonChat
              entries={chatEntries}
              colors={pawnColors}
              currentCharacterId={characterId}
              onSay={handleSay}
              canWrite={session.status === 'active'}
            />
          </div>
        )}
      </div>
      )}

      {leaderNote}
      {fleeModal}
      <ChallengeModal
          challenge={challenge}
          onFinish={handleChallengeFinish}
          onStep={handleChallengeStep}
          onClose={() => setChallenge(null)}
          use3D={view3D}
        />
    </div>
  );
};

// --- Session Header ---

interface SessionHeaderProps {
  session: SessionState;
  connected: boolean;
  reconnecting: boolean;
  /** Try the live line again after giving up. */
  onReconnect?: () => void;
  onBack: () => void;
  /** Tighter, for floating over the 3D table. */
  compact?: boolean;
  /** The 2D/3D switch, when the phase shows the map. */
  viewToggle?: ReactNode;
}

const SessionHeader = ({
  session,
  connected,
  reconnecting,
  onReconnect,
  onBack,
  compact = false,
  viewToggle,
}: SessionHeaderProps) => {
  const runOver = session.phase === 'finished' || session.phase === 'wiped';
  return (
    <div
      className={`bg-black/60 rounded-card backdrop-blur-sm flex flex-col ${
        compact ? 'p-3 gap-1.5' : 'p-4 sm:p-6 gap-2'
      }`}
    >
      {/* Over the table the column is narrow: everything stacks */}
      <div className={compact ? 'flex flex-col gap-1.5' : 'flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4'}>
        <button
          onClick={onBack}
          className="self-start flex items-center gap-2 text-white/60 hover:text-site-blue transition-colors text-sm"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          На локацию
        </button>

        <h1
          className={`gold-text font-medium uppercase flex-1 min-w-0 break-words ${
            compact ? 'text-base sm:text-lg' : 'text-lg sm:text-xl'
          }`}
        >
          {session.dungeon_name}
        </h1>

        <div className="flex flex-wrap items-center gap-3">
          {viewToggle}
          <span className="text-white/60 text-xs">{PHASE_LABELS[session.phase] ?? session.phase}</span>
          <span className="text-white/30 text-xs">{STABILITY_LABELS[session.stability_type] ?? ''}</span>
          {(session.floors ?? 1) > 1 && session.current_room && (
            <span className="text-gold/80 text-xs whitespace-nowrap">
              Этаж {session.current_room.floor ?? 1} из {session.floors}
            </span>
          )}
          {!runOver && (
            <div className="flex items-center gap-1.5">
              <div
                className={`w-2 h-2 rounded-full ${
                  connected ? 'bg-green-500' : reconnecting ? 'bg-yellow-500 animate-pulse' : 'bg-site-red'
                }`}
              />
              <span className="text-white/30 text-[10px]">
                {connected ? 'На связи' : reconnecting ? 'Переподключение...' : 'Нет связи'}
              </span>
              {!connected && !reconnecting && onReconnect && (
                <button type="button" onClick={onReconnect} className="site-link text-[10px] ml-1">
                  Переподключиться
                </button>
              )}
            </div>
          )}
        </div>
      </div>
      {session.abandon_at && session.phase !== 'distributing_loot' && (
        <p className="hidden sm:block text-white/30 text-[11px]">
          Если группа ничего не будет делать, забег будет считаться брошенным в{' '}
          {formatServerDateTime(session.abandon_at, DATE_TIME_SHORT)}.
        </p>
      )}
      {session.abandon_at && session.phase === 'distributing_loot' && (
        <p className="text-white/30 text-[11px]">
          Если добычу не поделить до {formatServerDateTime(session.abandon_at, DATE_TIME_SHORT)}, остаток уйдёт лидеру.
        </p>
      )}
    </div>
  );
};

// --- Skipped squadmates (party-run) ---

const SkippedMembersNotice = ({ members, onClose }: { members: SkippedMember[]; onClose: () => void }) => (
  <div className="rounded-card border border-gold-dark/40 bg-site-bg backdrop-blur-sm p-3 sm:p-4 flex gap-3" role="status">
    <div className="flex-1 min-w-0">
      <p className="text-gold text-sm font-medium mb-1">Не все сопартийцы вошли в подземелье:</p>
      {members.map((m) => (
        <p key={m.character_id} className="text-white/70 text-xs">
          {m.name ?? `Персонаж #${m.character_id}`} — {m.reason}
        </p>
      ))}
    </div>
    <button onClick={onClose} className="text-white/40 hover:text-site-blue transition-colors shrink-0 self-start" aria-label="Закрыть">
      ✕
    </button>
  </div>
);

// --- Move result banner ---

const moveBattleId = (move: MoveResponse): number | null =>
  (move.corridor_event?.type === 'battle' ? move.corridor_event.battle_id ?? null : null) ??
  (move.room_event?.type === 'battle_started' ? move.room_event.battle_id ?? null : null) ??
  (move.room_event?.followup?.type === 'battle_started' ? move.room_event.followup.battle_id ?? null : null);

const moveHasNews = (move: MoveResponse): boolean =>
  (!!move.corridor_event && move.corridor_event.type !== 'safe') || !!move.room_event;

interface BannerLine {
  tone: 'battle' | 'good' | 'bad' | 'info';
  title: string;
  text?: string;
}

const trapLine = (passed: boolean | null | undefined, message?: string | null, damage?: number | null): BannerLine => ({
  tone: passed ? 'good' : 'bad',
  title: passed ? 'Ловушка обезврежена!' : 'Ловушка сработала!',
  text: message ?? (!passed && damage ? `Урон каждому: ${damage}` : undefined),
});

const roomEventLines = (ev: RoomEvent | null | undefined, depth = 0): BannerLine[] => {
  if (!ev || depth > 3) return [];
  const mobs = ev.mob_names && ev.mob_names.length > 0 ? `Противники: ${ev.mob_names.join(', ')}` : undefined;
  switch (ev.type) {
    case 'battle_started':
      return [{ tone: 'battle', title: 'Бой начинается!', text: mobs }];
    case 'battle_error':
      return [{ tone: 'bad', title: 'Бой не начался', text: ev.message ?? 'Попробуйте ещё раз.' }];
    case 'trap_triggered':
      return [trapLine(ev.passed, ev.message, ev.damage)];
    case 'teleported':
      return [
        ev.fell
          ? { tone: 'bad', title: 'Провал!', text: ev.message ?? `Группа падает в «${ev.target_room_name ?? '???'}».` }
          : ev.red_portal
          ? { tone: 'bad', title: 'Красный портал!', text: ev.message ?? `Группу выбросило в «${ev.target_room_name ?? '???'}».` }
          : { tone: 'info', title: 'Телепорт!', text: `Группа перенесена в «${ev.target_room_name ?? '???'}».` },
        ...roomEventLines(ev.followup, depth + 1),
      ];
    case 'drop_spotted':
      return [{ tone: 'good', title: 'Провал замечен!', text: ev.message }];
    case 'portal_spotted':
      return [{ tone: ev.passed ? 'good' : 'info', title: ev.passed ? 'Ловушка распознана!' : 'Красный портал', text: ev.message }];
    case 'teleport_failed':
      return [{ tone: 'info', title: 'Портал не сработал', text: ev.message }];
    default:
      return ev.message ? [{ tone: 'info', title: ev.message }] : [];
  }
};

const TONE_CLASSES: Record<BannerLine['tone'], string> = {
  battle: 'text-red-300',
  good: 'text-green-300',
  bad: 'text-orange-300',
  info: 'text-cyan-300',
};

const MoveEventBanner = ({ move, onClose, onGoToBattle }: { move: MoveResponse; onClose: () => void; onGoToBattle: () => void }) => {
  const lines: BannerLine[] = [];
  const ce = move.corridor_event;
  if (ce?.type === 'battle') {
    lines.push({
      tone: 'battle',
      title: 'Засада в коридоре!',
      text: [ce.message, ce.mob_names?.length ? `Противники: ${ce.mob_names.join(', ')}` : null].filter(Boolean).join(' '),
    });
  } else if (ce?.type === 'trap') {
    lines.push(trapLine(ce.passed, ce.message, ce.damage));
  }
  lines.push(...roomEventLines(move.room_event));
  if (lines.length === 0) return null;
  const battleId = moveBattleId(move);

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className={`rounded-card p-4 backdrop-blur-sm border bg-site-bg ${battleId ? 'border-site-red/50' : 'border-white/15'}`}
      role="status"
    >
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0 flex flex-col gap-2">
          {lines.map((line, i) => (
            <div key={i}>
              <p className={`text-sm font-medium ${TONE_CLASSES[line.tone]}`}>{line.title}</p>
              {line.text && <p className="text-white/60 text-xs mt-0.5">{line.text}</p>}
            </div>
          ))}
          {move.stamina_consumed > 0 && (
            <p className="text-white/30 text-[11px]">Потрачено выносливости: {move.stamina_consumed}</p>
          )}
          {battleId && (
            <button onClick={onGoToBattle} className="btn-blue text-xs px-4 py-1.5 self-start">
              Перейти к бою
            </button>
          )}
        </div>
        <button onClick={onClose} className="text-white/40 hover:text-site-blue transition-colors shrink-0" aria-label="Закрыть">
          ✕
        </button>
      </div>
    </motion.div>
  );
};

// --- Ended run, loot still to share ---

const RunEndedNotice = ({ session, flee, onBack }: { session: SessionState; flee: FleeResponse | null; onBack: () => void }) => {
  const completed = session.status === 'completed';
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="bg-black/50 rounded-card p-4 sm:p-6 backdrop-blur-sm flex flex-col gap-3"
    >
      <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase">
        {completed ? 'Подземелье пройдено!' : 'Группа покинула подземелье'}
      </h2>
      {completed && session.cooldown_until && (
        <p className="text-white/60 text-sm">
          Подземелье закрыто на откат до {formatServerDateTime(session.cooldown_until, DATE_TIME_SHORT)}.
        </p>
      )}
      {!completed && flee && flee.items_lost.length > 0 && (
        <div className="bg-site-red/10 border border-site-red/20 rounded-card p-3">
          <p className="text-site-red text-xs font-medium mb-1">Потеряно при побеге:</p>
          <p className="text-site-red/80 text-xs">
            {flee.items_lost.map((i) => `${itemLabel(i)} ×${i.quantity}`).join(', ')}
          </p>
        </div>
      )}
      {!completed && !flee && (
        <p className="text-white/60 text-sm">При побеге часть добычи могла быть потеряна.</p>
      )}
      <p className="text-white/50 text-xs">
        Персонажи уже свободны: можно вернуться на локацию, а дележ подождёт.
      </p>
      <button onClick={onBack} className="btn-line text-sm px-5 py-2 self-start">
        На локацию
      </button>
    </motion.div>
  );
};

// --- Closed run ---

interface FinishedScreenProps {
  session: SessionState;
  finalize: FinalizeResponse | null;
  flee: FleeResponse | null;
  onBack: () => void;
}

const FinishedScreen = ({ session, finalize, flee, onBack }: FinishedScreenProps) => {
  const completed = session.status === 'completed';
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      className="bg-black/60 rounded-card p-6 sm:p-8 backdrop-blur-sm flex flex-col items-center gap-4 text-center"
    >
      <div className="text-5xl" aria-hidden>{completed ? '🏆' : '🚪'}</div>
      <h1 className="gold-text text-2xl sm:text-3xl font-medium uppercase">
        {completed ? 'Подземелье пройдено' : 'Забег завершён'}
      </h1>
      {completed && session.cooldown_until && (
        <p className="text-white/50 text-sm">
          Откат подземелья до {formatServerDateTime(session.cooldown_until, DATE_TIME_SHORT)}.
        </p>
      )}
      {flee && (
        <p className="text-white/60 text-sm">
          {flee.items_lost.length > 0
            ? `Потеряно при побеге: ${flee.items_lost.map((i) => `${itemLabel(i)} ×${i.quantity}`).join(', ')}.`
            : 'При побеге ничего не потеряно.'}
        </p>
      )}
      {!!finalize?.items_lost && (
        <p className="text-site-red/80 text-sm">Нерозданная добыча пропала: {finalize.items_lost} шт.</p>
      )}
      <button onClick={onBack} className="btn-blue text-sm sm:text-base px-8 py-3">
        Вернуться на локацию
      </button>
    </motion.div>
  );
};

// --- Wipe ---

const WipeScreen = ({ session, onBack }: { session: SessionState; onBack: () => void }) => {
  const until = parseServerDate(session.knocked_out_until);
  const stillOut = until ? until.getTime() > Date.now() : false;
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: 'easeOut' }}
      className="bg-black/60 rounded-card p-6 sm:p-8 backdrop-blur-sm flex flex-col items-center gap-4 text-center"
    >
      <div className="text-5xl" aria-hidden>💫</div>
      <h1 className="gold-text text-2xl sm:text-3xl font-medium uppercase">Группа пала</h1>
      <p className="text-white/80 text-sm sm:text-base max-w-xl leading-relaxed">
        Группа потеряла сознание, их вынесли из подземелья. Очнулись они уже снаружи — без добычи этого
        забега.
      </p>
      {until && (
        <p className="text-white/60 text-sm">
          {stillOut
            ? `Персонажи придут в себя в ${formatServerDateTime(session.knocked_out_until, TIME_ONLY)}. До этого действовать ими нельзя.`
            : 'Персонажи уже пришли в себя.'}
        </p>
      )}
      <button onClick={onBack} className="btn-blue text-sm sm:text-base px-8 py-3">
        Вернуться на локацию
      </button>
    </motion.div>
  );
};

export default DungeonSessionPage;
