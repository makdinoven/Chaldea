import { useEffect, useState, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchSessionState,
  moveDungeon,
  fleeDungeonThunk,
  clearMoveResponse,
  updateSessionFromWs,
  selectSessionState,
  selectStateLoading,
  selectDungeonsError,
  selectMoveLoading,
  selectFleeLoading,
  selectLastMoveResponse,
  selectLastFleeResponse,
} from '../../redux/slices/dungeonSlice';
import type { SessionState, MoveResponse } from '../../api/dungeons';
import type { DungeonWsMessage } from '../../hooks/useDungeonWebSocket';
import useDungeonWebSocket from '../../hooks/useDungeonWebSocket';
import DungeonMap from './DungeonMap';
import DungeonRoom from './DungeonRoom';
import DungeonPartyPanel from './DungeonPartyPanel';
import DungeonInventory from './DungeonInventory';
import DungeonLootDistribution from './DungeonLootDistribution';

// --- Mobile Tab ---

type MobileTab = 'map' | 'room' | 'party';

// --- Constants ---

const PHASE_LABELS: Record<string, string> = {
  forming: 'Формирование',
  exploring: 'Исследование',
  in_battle: 'В бою',
  in_event: 'Событие',
  distributing_loot: 'Распределение добычи',
  completed: 'Завершено',
  escaped: 'Побег',
  wiped: 'Гибель',
};

const STABILITY_LABELS: Record<string, string> = {
  static: 'Изученный',
  unstable: 'Опасный',
  chaotic: 'Смертельный',
};

// --- Component ---

const DungeonSessionPage = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();

  const sessionState = useAppSelector(selectSessionState);
  const loading = useAppSelector(selectStateLoading);
  const error = useAppSelector(selectDungeonsError);
  const moveLoading = useAppSelector(selectMoveLoading);
  const fleeLoading = useAppSelector(selectFleeLoading);
  const lastMoveResponse = useAppSelector(selectLastMoveResponse);
  const lastFleeResponse = useAppSelector(selectLastFleeResponse);

  const [showFleeModal, setShowFleeModal] = useState(false);
  const [showMoveEvent, setShowMoveEvent] = useState(false);
  const [mobileTab, setMobileTab] = useState<MobileTab>('map');
  const [isMoving, setIsMoving] = useState(false);
  const [movingToRoomId, setMovingToRoomId] = useState<number | null>(null);

  // WebSocket
  const token = typeof window !== 'undefined' ? localStorage.getItem('accessToken') : null;
  const { connected, reconnecting, lastMessage } = useDungeonWebSocket(
    sessionId ? Number(sessionId) : null,
    token,
  );

  // Get current character ID from Redux store
  const character = useAppSelector((state: { user: { character: { id: number } | null } }) => state.user.character);
  const currentCharacterId = character?.id ?? null;

  // Check if current user is leader
  const isLeader = useMemo(() => {
    if (!sessionState || !currentCharacterId) return false;
    return sessionState.members.some(
      (m) => m.character_id === currentCharacterId && m.is_leader,
    );
  }, [sessionState, currentCharacterId]);

  // Count dead members
  const deadMemberCount = useMemo(() => {
    if (!sessionState) return 0;
    return sessionState.members.filter((m) => m.status === 'dead').length;
  }, [sessionState]);

  // Fetch session state
  useEffect(() => {
    if (sessionId && currentCharacterId) {
      dispatch(fetchSessionState({ sessionId: Number(sessionId), characterId: currentCharacterId }));
    }
  }, [dispatch, sessionId, currentCharacterId]);

  // Handle WS messages
  useEffect(() => {
    if (!lastMessage) return;

    const msg = lastMessage as DungeonWsMessage;

    switch (msg.type) {
      case 'room_entered':
        setIsMoving(false);
        setMovingToRoomId(null);
        // Refetch full state
        if (sessionId) {
          dispatch(fetchSessionState({ sessionId: Number(sessionId), characterId: currentCharacterId! }));
        }
        break;

      case 'session_update':
        // Refetch full state
        if (sessionId) {
          dispatch(fetchSessionState({ sessionId: Number(sessionId), characterId: currentCharacterId! }));
        }
        break;

      case 'battle_started':
        toast('Начался бой!', { icon: '\u2694\uFE0F' });
        if (sessionId) {
          dispatch(fetchSessionState({ sessionId: Number(sessionId), characterId: currentCharacterId! }));
        }
        break;

      case 'battle_ended':
        toast.success('Бой завершён!');
        if (sessionId) {
          dispatch(fetchSessionState({ sessionId: Number(sessionId), characterId: currentCharacterId! }));
        }
        break;

      case 'member_status_changed': {
        const charName = (msg.data as { name?: string }).name ?? 'Участник';
        const status = (msg.data as { status?: string }).status;
        if (status === 'dead') {
          toast.error(`${charName} пал в бою!`);
        } else if (status === 'disconnected') {
          toast(`${charName} отключился`);
        }
        if (sessionId) {
          dispatch(fetchSessionState({ sessionId: Number(sessionId), characterId: currentCharacterId! }));
        }
        break;
      }

      case 'trap_triggered': {
        const trapMsg = (msg.data as { message?: string }).message;
        const passed = (msg.data as { passed?: boolean }).passed;
        if (passed) {
          toast.success(trapMsg ?? 'Ловушка обезврежена!');
        } else {
          toast.error(trapMsg ?? 'Ловушка сработала!');
        }
        break;
      }

      case 'loot_added': {
        const itemName = (msg.data as { item_name?: string }).item_name ?? 'Предмет';
        toast.success(`Получено: ${itemName}`);
        break;
      }

      case 'session_status': {
        const newStatus = (msg.data as { status?: string }).status;
        if (newStatus === 'completed') {
          toast.success('Подземелье пройдено!');
        } else if (newStatus === 'wiped') {
          toast.error('Отряд погиб...');
        }
        if (sessionId) {
          dispatch(fetchSessionState({ sessionId: Number(sessionId), characterId: currentCharacterId! }));
        }
        if (newStatus && 'session_state' in msg.data) {
          dispatch(updateSessionFromWs(msg.data.session_state as SessionState));
        }
        break;
      }

      case 'leader_changed':
        toast('Лидер группы изменён');
        if (sessionId) {
          dispatch(fetchSessionState({ sessionId: Number(sessionId), characterId: currentCharacterId! }));
        }
        break;

      case 'event_result': {
        const eventMsg = (msg.data as { message?: string }).message;
        if (eventMsg) {
          toast(eventMsg);
        }
        break;
      }

      default:
        break;
    }
  }, [lastMessage, dispatch, sessionId, currentCharacterId]);

  // Show move event notification when move completes
  useEffect(() => {
    if (!lastMoveResponse) return;

    // Reset moving state when move response arrives
    setIsMoving(false);
    setMovingToRoomId(null);

    if (lastMoveResponse.corridor_event) {
      setShowMoveEvent(true);
      // Auto-hide after 5 seconds
      const timer = setTimeout(() => {
        setShowMoveEvent(false);
        dispatch(clearMoveResponse());
      }, 5000);
      return () => clearTimeout(timer);
    } else {
      dispatch(clearMoveResponse());
    }
  }, [lastMoveResponse, dispatch]);

  // Handlers
  const handleMapMove = useCallback(
    (corridorId: number) => {
      if (!currentCharacterId || isMoving) return;

      // Find target room ID from the corridor
      const exit = sessionState?.current_room?.exits.find(
        (e) => e.corridor_id === corridorId,
      );
      if (exit) {
        setMovingToRoomId(exit.to_room_id);
      }

      setIsMoving(true);

      // Delay the actual move API call slightly to let animation start
      setTimeout(() => {
        dispatch(
          moveDungeon({
            sessionId: Number(sessionId),
            characterId: currentCharacterId,
            corridorId,
          }),
        );
      }, 100);
    },
    [currentCharacterId, isMoving, sessionState, dispatch, sessionId],
  );

  const handleFlee = useCallback(() => {
    if (!sessionId || !currentCharacterId) return;
    dispatch(fleeDungeonThunk({
      sessionId: Number(sessionId),
      characterId: currentCharacterId,
    }));
    setShowFleeModal(false);
  }, [dispatch, sessionId, currentCharacterId]);

  const handleGoToBattle = useCallback(() => {
    if (sessionState?.active_battle_id) {
      navigate(`/location/${sessionState.location_id}/battle/${sessionState.active_battle_id}`);
    }
  }, [navigate, sessionState?.active_battle_id]);

  // --- Loading state ---
  if (loading && !sessionState) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-10 h-10 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

  // --- Error state ---
  if (error && !sessionState) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <p className="text-white/60 text-lg">{error}</p>
        <button
          onClick={() => navigate(-1)}
          className="btn-blue text-sm px-6 py-2"
        >
          Назад
        </button>
      </div>
    );
  }

  if (!sessionState) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <p className="text-white/60 text-lg">Сессия не найдена</p>
        <button
          onClick={() => navigate(-1)}
          className="btn-blue text-sm px-6 py-2"
        >
          Назад
        </button>
      </div>
    );
  }

  const isTerminal = ['completed', 'escaped', 'wiped'].includes(sessionState.phase);

  // --- Terminal states ---
  if (isTerminal) {
    return (
      <TerminalScreen
        sessionState={sessionState}
        lastFleeResponse={lastFleeResponse}
        currentCharacterId={currentCharacterId}
        isLeader={isLeader}
        sessionId={Number(sessionId)}
        onBack={() => navigate(`/location/${sessionState.location_id}`)}
      />
    );
  }

  // --- In battle state ---
  if (sessionState.phase === 'in_battle') {
    return (
      <div className="flex flex-col gap-4 sm:gap-6 pb-10">
        <SessionHeader
          sessionState={sessionState}
          connected={connected}
          reconnecting={reconnecting}
          onBack={() => navigate(-1)}
        />

        <div className="bg-black/60 rounded-card p-6 sm:p-8 backdrop-blur-sm flex flex-col items-center gap-6 text-center">
          <div className="w-16 h-16 flex items-center justify-center text-4xl">
            {'\u2694\uFE0F'}
          </div>
          <div>
            <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase mb-2">
              Идёт бой!
            </h2>
            <p className="text-white/60 text-sm">
              Отряд сражается с врагами. Присоединитесь к бою.
            </p>
          </div>
          <button
            onClick={handleGoToBattle}
            className="btn-blue text-sm sm:text-base px-8 py-3"
          >
            Перейти к бою
          </button>
        </div>

        {/* Party panel */}
        <DungeonPartyPanel
          members={sessionState.members}
          maxSize={4}
          currentCharacterId={currentCharacterId}
          isLeader={isLeader}
        />
      </div>
    );
  }

  // --- Distributing loot ---
  if (sessionState.phase === 'distributing_loot') {
    return (
      <div className="flex flex-col gap-4 sm:gap-6 pb-10">
        <SessionHeader
          sessionState={sessionState}
          connected={connected}
          reconnecting={reconnecting}
          onBack={() => navigate(-1)}
        />

        <DungeonLootDistribution
          sessionId={Number(sessionId)}
          characterId={currentCharacterId ?? 0}
          groupInventory={sessionState.group_inventory}
          members={sessionState.members}
          isLeader={isLeader}
          onFinalized={() => navigate(`/location/${sessionState.location_id}`)}
        />

        {/* Party panel */}
        <DungeonPartyPanel
          members={sessionState.members}
          maxSize={4}
          currentCharacterId={currentCharacterId}
          isLeader={isLeader}
        />
      </div>
    );
  }

  // --- Exploring (main gameplay) ---
  return (
    <div className="flex flex-col gap-4 sm:gap-6 pb-10">
      <SessionHeader
        sessionState={sessionState}
        connected={connected}
        reconnecting={reconnecting}
        onBack={() => navigate(-1)}
      />

      {/* Move event notification */}
      <AnimatePresence>
        {showMoveEvent && lastMoveResponse?.corridor_event && (
          <MoveEventBanner
            moveResponse={lastMoveResponse}
            onClose={() => {
              setShowMoveEvent(false);
              dispatch(clearMoveResponse());
            }}
            onGoToBattle={handleGoToBattle}
          />
        )}
      </AnimatePresence>

      {/* Mobile tab bar */}
      <div className="flex lg:hidden bg-black/40 rounded-card p-1 backdrop-blur-sm">
        {(['map', 'room', 'party'] as MobileTab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setMobileTab(tab)}
            className={`flex-1 py-2 text-xs sm:text-sm font-medium rounded-card transition-colors ${
              mobileTab === tab
                ? 'bg-white/10 text-white'
                : 'text-white/40 hover:text-white/60'
            }`}
          >
            {tab === 'map' && 'Карта'}
            {tab === 'room' && 'Комната'}
            {tab === 'party' && 'Группа'}
          </button>
        ))}
      </div>

      {/* Desktop: 2-column layout — map primary (~70%), sidebar (320px) */}
      <div className="hidden lg:flex lg:gap-4">
        {/* Map — takes remaining space */}
        <div className="flex-1 min-w-0">
          <DungeonMap
            sessionState={sessionState}
            stabilityType="static"
            onMoveToRoom={handleMapMove}
            isMoving={isMoving}
            movingToRoomId={movingToRoomId}
          />
        </div>

        {/* Sidebar — room info, party, inventory, flee */}
        <div className="w-80 shrink-0 flex flex-col gap-4">
          {/* Current Room Info */}
          {sessionState.current_room && (
            <DungeonRoom
              room={sessionState.current_room}
              sessionId={Number(sessionId)}
              characterId={currentCharacterId ?? 0}
              isLeader={isLeader}
              moveLoading={moveLoading}
              deadMemberCount={deadMemberCount}
              members={sessionState.members}
              dungeonManaCoreCh={0}
            />
          )}

          {/* Party panel */}
          <DungeonPartyPanel
            members={sessionState.members}
            maxSize={4}
            currentCharacterId={currentCharacterId}
            isLeader={isLeader}
          />

          {/* Group inventory */}
          <DungeonInventory items={sessionState.group_inventory} compact />

          {/* Flee button */}
          {isLeader && (
            <button
              onClick={() => setShowFleeModal(true)}
              disabled={fleeLoading}
              className="text-sm px-4 py-2 rounded-card border border-site-red/40 text-site-red hover:bg-site-red/10 transition-colors disabled:opacity-50"
            >
              {fleeLoading ? 'Побег...' : 'Сбежать из подземелья'}
            </button>
          )}
        </div>
      </div>

      {/* Mobile: single column with tabs */}
      <div className="lg:hidden">
        {mobileTab === 'map' && (
          <DungeonMap
            sessionState={sessionState}
            stabilityType="static"
            onMoveToRoom={handleMapMove}
            isMoving={isMoving}
            movingToRoomId={movingToRoomId}
          />
        )}

        {mobileTab === 'room' && sessionState.current_room && (
          <DungeonRoom
            room={sessionState.current_room}
            sessionId={Number(sessionId)}
            characterId={currentCharacterId ?? 0}
            isLeader={isLeader}
            moveLoading={moveLoading}
            deadMemberCount={deadMemberCount}
            members={sessionState.members}
            dungeonManaCoreCh={0}
          />
        )}

        {mobileTab === 'party' && (
          <div className="flex flex-col gap-4">
            <DungeonPartyPanel
              members={sessionState.members}
              maxSize={4}
              currentCharacterId={currentCharacterId}
              isLeader={isLeader}
            />

            <DungeonInventory items={sessionState.group_inventory} />

            {isLeader && (
              <button
                onClick={() => setShowFleeModal(true)}
                disabled={fleeLoading}
                className="text-sm px-4 py-2 rounded-card border border-site-red/40 text-site-red hover:bg-site-red/10 transition-colors disabled:opacity-50"
              >
                {fleeLoading ? 'Побег...' : 'Сбежать из подземелья'}
              </button>
            )}
          </div>
        )}
      </div>

      {/* Flee confirmation modal */}
      <AnimatePresence>
        {showFleeModal && (
          <div className="modal-overlay" onClick={() => setShowFleeModal(false)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick max-w-sm w-full mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <h3 className="gold-text text-lg font-medium uppercase mb-3">
                Сбежать из подземелья?
              </h3>
              <p className="text-white/70 text-sm mb-2">
                Отряд развернётся и покинет подземелье.
              </p>
              <div className="bg-site-red/10 border border-site-red/30 rounded-card p-3 mb-4">
                <p className="text-site-red text-sm font-medium">
                  Внимание: каждый предмет в групповом инвентаре имеет 50% шанс быть потерян!
                </p>
              </div>

              {sessionState.group_inventory.length > 0 && (
                <div className="mb-4">
                  <p className="text-white/50 text-xs mb-1">
                    Под угрозой ({sessionState.group_inventory.length} предметов):
                  </p>
                  <div className="text-white/40 text-xs">
                    {sessionState.group_inventory.map((item) => (
                      <span key={item.item_id} className="mr-2">
                        {item.item_name} x{item.quantity}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex gap-3">
                <button
                  onClick={handleFlee}
                  disabled={fleeLoading}
                  className="text-sm px-5 py-2 flex-1 rounded-card bg-site-red/20 border border-site-red/40 text-site-red hover:bg-site-red/30 transition-colors disabled:opacity-50"
                >
                  {fleeLoading ? 'Побег...' : 'Сбежать'}
                </button>
                <button
                  onClick={() => setShowFleeModal(false)}
                  className="btn-line text-sm px-5 py-2 flex-1"
                >
                  Остаться
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};

// --- Session Header ---

interface SessionHeaderProps {
  sessionState: SessionState;
  connected: boolean;
  reconnecting: boolean;
  onBack: () => void;
}

const SessionHeader = ({ sessionState, connected, reconnecting, onBack }: SessionHeaderProps) => (
  <div className="bg-black/60 rounded-card p-4 sm:p-6 backdrop-blur-sm">
    <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
      <button
        onClick={onBack}
        className="self-start flex items-center gap-2 text-white/60 hover:text-white transition-colors text-sm"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Назад
      </button>

      <div className="flex-1 min-w-0">
        <h1 className="gold-text text-lg sm:text-xl font-medium uppercase truncate">
          {sessionState.dungeon_name}
        </h1>
      </div>

      <div className="flex items-center gap-3">
        <span className="text-white/40 text-xs">
          {PHASE_LABELS[sessionState.phase] ?? sessionState.phase}
        </span>

        {/* Connection status */}
        <div className="flex items-center gap-1.5">
          <div
            className={`w-2 h-2 rounded-full ${
              connected ? 'bg-green-500' : reconnecting ? 'bg-yellow-500 animate-pulse' : 'bg-site-red'
            }`}
          />
          <span className="text-white/30 text-[10px]">
            {connected ? 'Подключено' : reconnecting ? 'Переподключение...' : 'Нет связи'}
          </span>
        </div>
      </div>
    </div>
  </div>
);

// --- Move Event Banner ---

interface MoveEventBannerProps {
  moveResponse: MoveResponse;
  onClose: () => void;
  onGoToBattle: () => void;
}

const MoveEventBanner = ({ moveResponse, onClose, onGoToBattle }: MoveEventBannerProps) => {
  const event = moveResponse.corridor_event;
  if (!event) return null;

  const isBattle = event.type === 'battle';
  const isTrap = event.type === 'trap';

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className={`rounded-card p-4 backdrop-blur-sm border ${
        isBattle
          ? 'bg-red-900/30 border-red-600/30'
          : isTrap
            ? event.passed
              ? 'bg-green-900/30 border-green-600/30'
              : 'bg-orange-900/30 border-orange-600/30'
            : 'bg-white/5 border-white/10'
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="text-2xl shrink-0">
          {isBattle ? '\u2694\uFE0F' : isTrap ? (event.passed ? '\u2705' : '\u26A0\uFE0F') : '\u2728'}
        </div>
        <div className="flex-1 min-w-0">
          {isBattle && (
            <>
              <p className="text-red-300 text-sm font-medium mb-1">Засада в коридоре!</p>
              <p className="text-white/60 text-xs mb-2">
                {event.message ?? 'На вас напали по дороге!'}
              </p>
              <button
                onClick={onGoToBattle}
                className="btn-blue text-xs px-4 py-1.5"
              >
                Перейти к бою
              </button>
            </>
          )}
          {isTrap && (
            <>
              <p className={`text-sm font-medium mb-1 ${event.passed ? 'text-green-300' : 'text-orange-300'}`}>
                {event.passed ? 'Ловушка обезврежена!' : 'Ловушка сработала!'}
              </p>
              <p className="text-white/60 text-xs">
                {event.message ?? (event.passed
                  ? `${event.best_character ?? 'Кто-то'} заметил ловушку вовремя.`
                  : 'Отряд попал в ловушку.')}
              </p>
            </>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-white/40 hover:text-white transition-colors shrink-0"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </motion.div>
  );
};

// --- Terminal Screen ---

interface TerminalScreenProps {
  sessionState: SessionState;
  lastFleeResponse: { items_lost: { item_id: number; item_name: string; quantity: number }[]; items_remaining: { item_id: number; item_name: string; quantity: number }[]; message: string } | null;
  currentCharacterId: number | null;
  isLeader: boolean;
  sessionId: number;
  onBack: () => void;
}

const TerminalScreen = ({ sessionState, lastFleeResponse, currentCharacterId, isLeader, sessionId, onBack }: TerminalScreenProps) => {
  const isCompleted = sessionState.phase === 'completed';
  const isEscaped = sessionState.phase === 'escaped';
  const isWiped = sessionState.phase === 'wiped';

  const [showLootDistribution, setShowLootDistribution] = useState(false);

  // Auto-show loot distribution for completed/escaped if there's loot
  const hasLoot = (isCompleted || isEscaped) && sessionState.group_inventory.length > 0;

  return (
    <div className="flex flex-col gap-4 sm:gap-6 pb-10">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
        className="bg-black/60 rounded-card p-6 sm:p-8 backdrop-blur-sm flex flex-col items-center gap-6 text-center"
      >
        <div className="w-20 h-20 flex items-center justify-center text-5xl">
          {isCompleted && '\uD83C\uDFC6'}
          {isEscaped && '\uD83C\uDFC3'}
          {isWiped && '\uD83D\uDC80'}
        </div>

        <div>
          <h1 className="gold-text text-2xl sm:text-3xl font-medium uppercase mb-2">
            {isCompleted && 'Подземелье пройдено!'}
            {isEscaped && 'Группа сбежала!'}
            {isWiped && 'Все пали...'}
          </h1>
          <p className="text-white/60 text-sm sm:text-base">
            {isCompleted && 'Поздравляем! Ваш отряд успешно прошёл подземелье.'}
            {isEscaped && (lastFleeResponse?.message ?? 'Отряд покинул подземелье. Часть добычи потеряна.')}
            {isWiped && 'Все члены отряда пали. Подземелье поглотило героев...'}
          </p>
        </div>

        {/* Flee details */}
        {isEscaped && lastFleeResponse && (
          <div className="w-full max-w-md">
            {lastFleeResponse.items_lost.length > 0 && (
              <div className="bg-site-red/10 border border-site-red/20 rounded-card p-3 mb-3 text-left">
                <p className="text-site-red text-xs font-medium mb-1">Потерянные предметы:</p>
                {lastFleeResponse.items_lost.map((item) => (
                  <p key={item.item_id} className="text-site-red/70 text-xs">
                    {item.item_name} x{item.quantity}
                  </p>
                ))}
              </div>
            )}
            {lastFleeResponse.items_remaining.length > 0 && (
              <div className="bg-green-900/20 border border-green-600/20 rounded-card p-3 text-left">
                <p className="text-green-400 text-xs font-medium mb-1">Сохранённые предметы:</p>
                {lastFleeResponse.items_remaining.map((item) => (
                  <p key={item.item_id} className="text-green-300/70 text-xs">
                    {item.item_name} x{item.quantity}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Party summary */}
        <div className="w-full max-w-md">
          <DungeonPartyPanel
            members={sessionState.members}
            maxSize={4}
            currentCharacterId={currentCharacterId}
            isLeader={false}
          />
        </div>

        {/* Actions */}
        {hasLoot && !showLootDistribution && (
          <button
            onClick={() => setShowLootDistribution(true)}
            className="btn-blue text-sm sm:text-base px-8 py-3"
          >
            Распределить добычу
          </button>
        )}

        {isWiped && (
          <button
            onClick={onBack}
            className="btn-blue text-sm sm:text-base px-8 py-3"
          >
            Вернуться
          </button>
        )}

        {!hasLoot && !isWiped && (
          <button
            onClick={onBack}
            className="btn-blue text-sm sm:text-base px-8 py-3"
          >
            Вернуться
          </button>
        )}
      </motion.div>

      {/* Loot distribution */}
      {showLootDistribution && (
        <DungeonLootDistribution
          sessionId={sessionId}
          characterId={currentCharacterId ?? 0}
          groupInventory={sessionState.group_inventory}
          members={sessionState.members}
          isLeader={isLeader}
          onFinalized={onBack}
        />
      )}
    </div>
  );
};

export default DungeonSessionPage;
