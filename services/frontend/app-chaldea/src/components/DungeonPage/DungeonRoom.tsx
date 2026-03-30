import { useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  interactRoom,
  fetchSessionState,
  selectInteractLoading,
  selectLastInteractResponse,
  clearInteractResponse,
} from '../../redux/slices/dungeonSlice';
import useCountdown from '../../hooks/useCountdown';
import type { RoomView, InteractResponse, SessionMember } from '../../api/dungeons';

// --- Types ---

interface DungeonRoomProps {
  room: RoomView;
  sessionId: number;
  characterId: number;
  isLeader: boolean;
  moveLoading: boolean;
  deadMemberCount: number;
  members: SessionMember[];
  dungeonManaCoreCh: number;
}

// --- Constants ---

const ROOM_TYPE_BADGES: Record<string, { label: string; color: string }> = {
  battle: { label: 'Бой', color: 'bg-red-600/80 text-red-100' },
  boss: { label: 'Босс', color: 'bg-red-900/80 text-red-100' },
  treasure: { label: 'Сокровищница', color: 'bg-yellow-600/80 text-yellow-100' },
  trap: { label: 'Ловушка', color: 'bg-orange-600/80 text-orange-100' },
  event: { label: 'Событие', color: 'bg-purple-600/80 text-purple-100' },
  rest: { label: 'Отдых', color: 'bg-green-600/80 text-green-100' },
  merchant: { label: 'Торговец', color: 'bg-site-blue/40 text-site-blue' },
  fork: { label: 'Развилка', color: 'bg-white/10 text-white/70' },
  teleport: { label: 'Телепорт', color: 'bg-cyan-600/80 text-cyan-100' },
  deadend: { label: 'Тупик', color: 'bg-amber-900/80 text-amber-200' },
  mana_core: { label: 'Ядро маны', color: 'bg-yellow-500/80 text-yellow-900' },
};

// --- Component ---

const DungeonRoom = ({
  room,
  sessionId,
  characterId,
  isLeader,
  moveLoading,
  deadMemberCount,
  members,
  dungeonManaCoreCh,
}: DungeonRoomProps) => {
  const dispatch = useAppDispatch();
  const interactLoading = useAppSelector(selectInteractLoading);
  const lastInteractResponse = useAppSelector(selectLastInteractResponse);

  const badge = ROOM_TYPE_BADGES[room.room_type] ?? { label: room.room_type, color: 'bg-white/10 text-white/70' };

  const handleInteract = useCallback(
    (action: string, extraData?: Record<string, unknown>) => {
      dispatch(clearInteractResponse());
      dispatch(interactRoom({ sessionId, characterId, action, extraData })).then(() => {
        dispatch(fetchSessionState({ sessionId, characterId }));
      });
    },
    [dispatch, sessionId, characterId],
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="bg-black/40 rounded-card p-4 sm:p-6 backdrop-blur-sm flex flex-col gap-4"
    >
      {/* Room header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2">
        <h2 className="gold-text text-lg sm:text-xl font-medium flex-1 min-w-0">
          {room.name}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`text-[10px] sm:text-xs px-2 py-0.5 rounded-full font-medium ${badge.color}`}>
            {badge.label}
          </span>
          {room.is_cleared && (
            <span className="text-[10px] sm:text-xs px-2 py-0.5 rounded-full font-medium bg-green-600/40 text-green-300">
              Зачищена
            </span>
          )}
        </div>
      </div>

      {/* Room image */}
      {room.image_url && (
        <div className="rounded-card overflow-hidden max-h-48">
          <img
            src={room.image_url}
            alt={room.name}
            className="w-full h-full object-cover"
          />
        </div>
      )}

      {/* Room description */}
      <p className="text-white/70 text-sm leading-relaxed">
        {room.description}
      </p>

      {/* Room-specific content */}
      <RoomContent
        room={room}
        isLeader={isLeader}
        interactLoading={interactLoading}
        lastInteractResponse={lastInteractResponse}
        members={members}
        dungeonManaCoreCh={dungeonManaCoreCh}
        onInteract={handleInteract}
      />

      {/* Exits info (navigation is via the interactive map) */}
      {room.exits.length === 0 && (
        <p className="text-white/40 text-sm italic">Нет доступных выходов</p>
      )}
    </motion.div>
  );
};

// --- Room Content sub-component ---

interface RoomContentProps {
  room: RoomView;
  isLeader: boolean;
  interactLoading: boolean;
  lastInteractResponse: InteractResponse | null;
  members: SessionMember[];
  dungeonManaCoreCh: number;
  onInteract: (action: string, extraData?: Record<string, unknown>) => void;
}

const RoomContent = ({
  room,
  isLeader,
  interactLoading,
  lastInteractResponse,
  members,
  dungeonManaCoreCh,
  onInteract,
}: RoomContentProps) => {
  const cfg = room.room_config_visible ?? {};

  switch (room.room_type) {
    case 'battle':
      return <BattleRoomContent room={room} cfg={cfg} isBoss={false} />;
    case 'boss':
      return (
        <BossRoomContent
          room={room}
          cfg={cfg}
          isLeader={isLeader}
          interactLoading={interactLoading}
          lastInteractResponse={lastInteractResponse}
          dungeonManaCoreCh={dungeonManaCoreCh}
          onInteract={onInteract}
        />
      );
    case 'treasure':
      return (
        <TreasureRoomContent
          room={room}
          isLeader={isLeader}
          interactLoading={interactLoading}
          lastInteractResponse={lastInteractResponse}
          onInteract={onInteract}
        />
      );
    case 'trap':
      return <TrapRoomContent room={room} cfg={cfg} />;
    case 'event':
      return (
        <EventRoomContent
          room={room}
          cfg={cfg}
          isLeader={isLeader}
          interactLoading={interactLoading}
          lastInteractResponse={lastInteractResponse}
          onInteract={onInteract}
        />
      );
    case 'rest':
      return (
        <RestRoomContent
          room={room}
          cfg={cfg}
          isLeader={isLeader}
          interactLoading={interactLoading}
          lastInteractResponse={lastInteractResponse}
          members={members}
          onInteract={onInteract}
        />
      );
    case 'merchant':
      return (
        <MerchantRoomContent
          room={room}
          cfg={cfg}
          isLeader={isLeader}
          interactLoading={interactLoading}
          onInteract={onInteract}
        />
      );
    case 'teleport':
      return <TeleportRoomContent cfg={cfg} />;
    case 'fork':
      return <ForkRoomContent />;
    case 'deadend':
      return <DeadendRoomContent />;
    case 'mana_core':
      return (
        <ManaCoreRoomContent
          room={room}
          isLeader={isLeader}
          interactLoading={interactLoading}
          lastInteractResponse={lastInteractResponse}
          dungeonManaCoreCh={dungeonManaCoreCh}
          onInteract={onInteract}
        />
      );
    default:
      return null;
  }
};

// --- Battle Room ---

const BattleRoomContent = ({
  room,
  cfg,
  isBoss,
}: {
  room: RoomView;
  cfg: Record<string, unknown>;
  isBoss: boolean;
}) => {
  const navigate = useNavigate();
  const mobNames = cfg.mob_names as string[] | undefined;
  const activeBattleId = cfg.active_battle_id as number | undefined;
  const inBattle = cfg.in_battle === true || !!activeBattleId;

  if (room.is_cleared) {
    const clearedAt = cfg.cleared_at as string | undefined;
    return (
      <div className="bg-green-900/20 rounded-card px-4 py-3 border border-green-600/20">
        <div className="flex items-center gap-2">
          <span className="text-green-400 text-base">&#10003;</span>
          <p className="text-green-300 text-sm font-medium">Комната зачищена</p>
        </div>
        {clearedAt && (
          <p className="text-white/30 text-xs mt-1">
            {new Date(clearedAt).toLocaleString('ru-RU')}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className={`rounded-card px-4 py-3 border ${isBoss ? 'bg-red-950/30 border-red-700/30' : 'bg-red-900/20 border-red-600/20'}`}>
      <p className={`text-sm font-medium mb-2 ${isBoss ? 'text-red-200' : 'text-red-300'}`}>
        {isBoss ? 'Здесь обитает могущественный враг!' : 'В этой комнате враги!'}
      </p>

      {mobNames && mobNames.length > 0 && (
        <div className="mb-2">
          <p className="text-white/40 text-xs mb-1">Противники:</p>
          <div className="flex flex-wrap gap-1">
            {mobNames.map((name, i) => (
              <span key={i} className="text-red-300/70 text-xs bg-red-900/30 px-2 py-0.5 rounded-full">
                {name}
              </span>
            ))}
          </div>
        </div>
      )}

      {inBattle && (
        <div className="mt-2 flex flex-col sm:flex-row sm:items-center gap-2">
          <p className="text-yellow-300 text-sm font-medium animate-pulse">Бой идёт!</p>
          {activeBattleId && (
            <button
              onClick={() => navigate(`/battles/${activeBattleId}`)}
              className="btn-blue text-xs px-4 py-1.5"
            >
              Перейти к бою
            </button>
          )}
        </div>
      )}
    </div>
  );
};

// --- Boss Room ---

const BossRoomContent = ({
  room,
  cfg,
  isLeader,
  interactLoading,
  lastInteractResponse,
  dungeonManaCoreCh,
  onInteract,
}: {
  room: RoomView;
  cfg: Record<string, unknown>;
  isLeader: boolean;
  interactLoading: boolean;
  lastInteractResponse: InteractResponse | null;
  dungeonManaCoreCh: number;
  onInteract: (action: string, extraData?: Record<string, unknown>) => void;
}) => {
  const lootCollected = cfg.loot_collected === true;
  const manaCoreAccessible = cfg.mana_core_accessible === true;

  if (!room.is_cleared) {
    return <BattleRoomContent room={room} cfg={cfg} isBoss={true} />;
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Cleared message */}
      <div className="bg-green-900/20 rounded-card px-4 py-3 border border-green-600/20">
        <div className="flex items-center gap-2">
          <span className="text-green-400 text-base">&#10003;</span>
          <p className="text-green-300 text-sm font-medium">Босс повержен!</p>
        </div>
      </div>

      {/* Loot chest */}
      {!lootCollected && isLeader && (
        <button
          onClick={() => onInteract('open_chest')}
          disabled={interactLoading}
          className="relative overflow-hidden bg-yellow-900/20 rounded-card px-4 py-4 border border-yellow-600/30 text-left
            hover:bg-yellow-900/30 transition-colors disabled:opacity-50 group"
        >
          <div className="flex items-center gap-3">
            <ChestIcon />
            <div>
              <p className="text-yellow-300 text-sm font-medium">Открыть главный сундук</p>
              <p className="text-white/40 text-xs mt-0.5">Награда за победу над боссом</p>
            </div>
          </div>
        </button>
      )}
      {lootCollected && (
        <div className="bg-white/5 rounded-card px-4 py-3">
          <p className="text-white/40 text-sm">Сундук уже открыт</p>
        </div>
      )}

      {/* Loot display */}
      <LootDisplay response={lastInteractResponse} />

      {/* Mana core notification */}
      {manaCoreAccessible && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
          className="bg-yellow-500/10 rounded-card px-4 py-4 border-2 border-yellow-500/40 animate-pulse"
        >
          <p className="text-yellow-300 text-sm font-medium">
            Найдена скрытая комната!
          </p>
          <p className="text-white/50 text-xs mt-1">
            За поверженным боссом открылся проход к Ядру маны...
          </p>
        </motion.div>
      )}
    </div>
  );
};

// --- Treasure Room ---

const TreasureRoomContent = ({
  room,
  isLeader,
  interactLoading,
  lastInteractResponse,
  onInteract,
}: {
  room: RoomView;
  isLeader: boolean;
  interactLoading: boolean;
  lastInteractResponse: InteractResponse | null;
  onInteract: (action: string) => void;
}) => {
  const [chestOpened, setChestOpened] = useState(false);
  const cfg = room.room_config_visible ?? {};
  const lootCollected = cfg.loot_collected === true;

  if (room.is_cleared || lootCollected) {
    return (
      <div className="flex flex-col gap-3">
        <div className="bg-white/5 rounded-card px-4 py-3 flex items-center gap-3">
          <ChestIcon opened />
          <p className="text-white/40 text-sm">Сундук пуст</p>
        </div>
        <LootDisplay response={lastInteractResponse} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="bg-yellow-900/20 rounded-card px-4 py-4 border border-yellow-600/20">
        <div className="flex items-center gap-3">
          <motion.div
            animate={chestOpened ? { rotateY: 180, scale: 1.1 } : {}}
            transition={{ duration: 0.5 }}
          >
            <ChestIcon opened={chestOpened} />
          </motion.div>
          <div className="flex-1">
            <p className="text-yellow-300 text-sm font-medium">
              Вы видите сундук с сокровищами!
            </p>
            {isLeader && (
              <button
                onClick={() => {
                  setChestOpened(true);
                  onInteract('open_chest');
                }}
                disabled={interactLoading}
                className="btn-blue text-xs px-4 py-1.5 mt-2 disabled:opacity-50"
              >
                {interactLoading ? 'Открываем...' : 'Открыть сундук'}
              </button>
            )}
            {!isLeader && (
              <p className="text-white/30 text-xs mt-1">Только лидер может открыть сундук</p>
            )}
          </div>
        </div>
      </div>
      <LootDisplay response={lastInteractResponse} />
    </div>
  );
};

// --- Trap Room ---

const TrapRoomContent = ({
  room,
  cfg,
}: {
  room: RoomView;
  cfg: Record<string, unknown>;
}) => {
  const statName = cfg.stat_name as string | undefined;
  const difficulty = cfg.difficulty as number | undefined;
  const trapDescription = cfg.description as string | undefined;
  const passed = cfg.passed as boolean | undefined;
  const resultMessage = cfg.result_message as string | undefined;
  const bestCharacter = cfg.best_character as string | undefined;
  const bestValue = cfg.best_value as number | undefined;

  if (room.is_cleared) {
    return (
      <div className={`rounded-card px-4 py-3 border ${passed ? 'bg-green-900/20 border-green-600/20' : 'bg-orange-900/20 border-orange-600/20'}`}>
        <p className={`text-sm font-medium ${passed ? 'text-green-300' : 'text-orange-300'}`}>
          {passed ? 'Ловушка обезврежена' : 'Ловушка сработала'}
        </p>
        {resultMessage && (
          <p className="text-white/50 text-xs mt-1">{resultMessage}</p>
        )}
        {bestCharacter && (
          <p className="text-white/30 text-xs mt-1">
            Проверку прошёл: {bestCharacter}{bestValue !== undefined ? ` (${bestValue})` : ''}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="bg-orange-900/20 rounded-card px-4 py-3 border border-orange-600/20">
      {trapDescription && (
        <p className="text-orange-200 text-sm mb-2">{trapDescription}</p>
      )}
      {!trapDescription && (
        <p className="text-orange-300 text-sm mb-2">Вы чувствуете опасность...</p>
      )}
      {statName && difficulty !== undefined && (
        <p className="text-white/50 text-xs">
          Проверка: <span className="text-orange-300">{statName}</span>, сложность: <span className="text-orange-300">{difficulty}</span>
        </p>
      )}
      <p className="text-white/30 text-xs mt-1 italic">
        Ловушка сработает автоматически
      </p>
    </div>
  );
};

// --- Event Room ---

const EventRoomContent = ({
  room,
  cfg,
  isLeader,
  interactLoading,
  lastInteractResponse,
  onInteract,
}: {
  room: RoomView;
  cfg: Record<string, unknown>;
  isLeader: boolean;
  interactLoading: boolean;
  lastInteractResponse: InteractResponse | null;
  onInteract: (action: string, extraData?: Record<string, unknown>) => void;
}) => {
  const eventText = cfg.text as string | undefined;
  const choices = cfg.choices as string[] | undefined;
  const choiceMade = cfg.choice_made as number | undefined;
  const outcomeMessage = cfg.outcome_message as string | undefined;

  if (room.is_cleared || choiceMade !== undefined) {
    return (
      <div className="bg-purple-900/20 rounded-card px-4 py-4 border border-purple-600/20">
        {eventText && (
          <p className="text-purple-200/80 text-sm italic leading-relaxed mb-3 border-l-2 border-purple-500/30 pl-3">
            {eventText}
          </p>
        )}
        <div className="bg-purple-800/20 rounded-card px-3 py-2">
          <p className="text-white/40 text-xs mb-1">Ваш выбор:</p>
          {choices && choiceMade !== undefined && choices[choiceMade] && (
            <p className="text-purple-300 text-sm font-medium">{choices[choiceMade]}</p>
          )}
          {outcomeMessage && (
            <p className="text-white/60 text-sm mt-2">{outcomeMessage}</p>
          )}
          {lastInteractResponse?.message && lastInteractResponse.action === 'event_choice' && (
            <p className="text-white/60 text-sm mt-2">{lastInteractResponse.message}</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-purple-900/20 rounded-card px-4 py-4 border border-purple-600/20">
      {eventText && (
        <p className="text-purple-200/90 text-sm italic leading-relaxed mb-4 border-l-2 border-purple-500/30 pl-3">
          {eventText}
        </p>
      )}
      {choices && choices.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-white/40 text-xs uppercase tracking-wide">Выберите действие:</p>
          {choices.map((choice, idx) => (
            <button
              key={idx}
              onClick={() => onInteract('event_choice', { choice_index: idx })}
              disabled={interactLoading || !isLeader}
              className="text-left bg-purple-800/20 hover:bg-purple-800/40 rounded-card px-4 py-3
                border border-purple-500/20 hover:border-purple-500/40
                text-purple-200 text-sm transition-colors disabled:opacity-50"
            >
              {choice}
            </button>
          ))}
          {!isLeader && (
            <p className="text-white/30 text-xs italic">Только лидер принимает решение</p>
          )}
        </div>
      )}
    </div>
  );
};

// --- Rest Room ---

const RestRoomContent = ({
  room,
  cfg,
  isLeader,
  interactLoading,
  lastInteractResponse,
  members,
  onInteract,
}: {
  room: RoomView;
  cfg: Record<string, unknown>;
  isLeader: boolean;
  interactLoading: boolean;
  lastInteractResponse: InteractResponse | null;
  members: SessionMember[];
  onInteract: (action: string, extraData?: Record<string, unknown>) => void;
}) => {
  const healPercent = cfg.heal_percent as number | undefined;
  const waitSeconds = cfg.wait_seconds as number | undefined;
  const goldCost = cfg.gold_cost as number | undefined;
  const restStartedAt = cfg.rest_started_at as number | undefined;
  const restComplete = cfg.rest_complete === true;
  const reviveCost = cfg.revive_cost as number | undefined;
  const recoveryInfo = cfg.recovery_info as Record<string, number> | undefined;

  const restEndTimestamp = useMemo(() => {
    if (!restStartedAt || !waitSeconds) return null;
    return restStartedAt + waitSeconds;
  }, [restStartedAt, waitSeconds]);

  const { formatted, isDone } = useCountdown(restEndTimestamp);
  const deadMembers = members.filter((m) => m.status === 'dead');

  // Rest not started
  if (!restStartedAt && !restComplete) {
    return (
      <div className="bg-green-900/20 rounded-card px-4 py-4 border border-green-600/20">
        <p className="text-green-300 text-sm font-medium mb-3">
          Место отдыха. Можно восстановить силы.
        </p>

        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-white/50 mb-3">
          {healPercent !== undefined && (
            <span>Восстановление: <span className="text-green-300">{healPercent}%</span></span>
          )}
          {waitSeconds !== undefined && (
            <span>Время ожидания: <span className="text-green-300">{Math.floor(waitSeconds / 60)} мин.</span></span>
          )}
          {goldCost !== undefined && goldCost > 0 && (
            <span>Стоимость: <span className="text-yellow-300">{goldCost} золота</span></span>
          )}
        </div>

        {isLeader && (
          <button
            onClick={() => onInteract('start_rest')}
            disabled={interactLoading}
            className="btn-blue text-xs px-4 py-1.5 disabled:opacity-50"
          >
            {interactLoading ? 'Начинаем...' : 'Отдохнуть'}
          </button>
        )}
        {!isLeader && (
          <p className="text-white/30 text-xs italic">Только лидер может начать отдых</p>
        )}

        {/* Revive section */}
        {deadMembers.length > 0 && (
          <ReviveSection
            deadMembers={deadMembers}
            reviveCost={reviveCost ?? 0}
            isLeader={isLeader}
            interactLoading={interactLoading}
            onInteract={onInteract}
          />
        )}
      </div>
    );
  }

  // Rest in progress (counting down)
  if (restStartedAt && !restComplete && !isDone) {
    return (
      <div className="bg-green-900/20 rounded-card px-4 py-4 border border-green-600/20">
        <p className="text-green-300 text-sm font-medium mb-3">Отряд отдыхает...</p>
        <div className="flex items-center gap-3 mb-3">
          <div className="w-12 h-12 rounded-full border-2 border-green-500/40 flex items-center justify-center">
            <span className="text-green-300 text-sm font-mono font-medium">{formatted}</span>
          </div>
          <p className="text-white/40 text-xs">Осталось до окончания отдыха</p>
        </div>

        {/* Revive section during rest */}
        {deadMembers.length > 0 && (
          <ReviveSection
            deadMembers={deadMembers}
            reviveCost={reviveCost ?? 0}
            isLeader={isLeader}
            interactLoading={interactLoading}
            onInteract={onInteract}
          />
        )}
      </div>
    );
  }

  // Rest done, can complete
  if ((isDone && restStartedAt && !restComplete) || restComplete) {
    return (
      <div className="bg-green-900/20 rounded-card px-4 py-4 border border-green-600/20">
        {restComplete ? (
          <>
            <p className="text-green-300 text-sm font-medium mb-2">Отдых завершён!</p>
            {recoveryInfo && (
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-white/50">
                {recoveryInfo.hp !== undefined && (
                  <span>HP: <span className="text-green-300">+{recoveryInfo.hp}</span></span>
                )}
                {recoveryInfo.stamina !== undefined && (
                  <span>Стамина: <span className="text-stat-stamina">+{recoveryInfo.stamina}</span></span>
                )}
                {recoveryInfo.mana !== undefined && (
                  <span>Мана: <span className="text-stat-mana">+{recoveryInfo.mana}</span></span>
                )}
              </div>
            )}
            {lastInteractResponse?.message && lastInteractResponse.action === 'complete_rest' && (
              <p className="text-white/50 text-xs mt-2">{lastInteractResponse.message}</p>
            )}
          </>
        ) : (
          <>
            <p className="text-green-300 text-sm font-medium mb-3">Отдых окончен!</p>
            {isLeader && (
              <button
                onClick={() => onInteract('complete_rest')}
                disabled={interactLoading}
                className="btn-blue text-xs px-4 py-1.5 disabled:opacity-50"
              >
                {interactLoading ? 'Завершаем...' : 'Завершить отдых'}
              </button>
            )}
          </>
        )}

        {/* Revive section */}
        {deadMembers.length > 0 && (
          <ReviveSection
            deadMembers={deadMembers}
            reviveCost={reviveCost ?? 0}
            isLeader={isLeader}
            interactLoading={interactLoading}
            onInteract={onInteract}
          />
        )}
      </div>
    );
  }

  return null;
};

// --- Revive Section ---

const ReviveSection = ({
  deadMembers,
  reviveCost,
  isLeader,
  interactLoading,
  onInteract,
}: {
  deadMembers: SessionMember[];
  reviveCost: number;
  isLeader: boolean;
  interactLoading: boolean;
  onInteract: (action: string, extraData?: Record<string, unknown>) => void;
}) => {
  const [confirmRevive, setConfirmRevive] = useState<number | null>(null);

  return (
    <div className="mt-4 pt-3 border-t border-green-600/20">
      <p className="text-white/50 text-xs uppercase tracking-wide mb-2">Павшие союзники</p>
      <div className="flex flex-col gap-2">
        {deadMembers.map((member) => (
          <div key={member.character_id} className="flex items-center justify-between bg-red-900/10 rounded-card px-3 py-2">
            <div className="flex items-center gap-2">
              <span className="text-red-400 text-xs">&#9760;</span>
              <span className="text-white/60 text-sm">{member.name}</span>
            </div>
            {isLeader && (
              <>
                {confirmRevive === member.character_id ? (
                  <div className="flex items-center gap-2">
                    <span className="text-yellow-300 text-xs">{reviveCost} золота</span>
                    <button
                      onClick={() => {
                        onInteract('revive_member', { target_character_id: member.character_id });
                        setConfirmRevive(null);
                      }}
                      disabled={interactLoading}
                      className="text-xs px-2 py-1 rounded bg-green-600/20 text-green-300 hover:bg-green-600/30 transition-colors disabled:opacity-50"
                    >
                      {interactLoading ? '...' : 'Да'}
                    </button>
                    <button
                      onClick={() => setConfirmRevive(null)}
                      className="text-xs px-2 py-1 rounded bg-white/5 text-white/40 hover:bg-white/10 transition-colors"
                    >
                      Нет
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setConfirmRevive(member.character_id)}
                    disabled={interactLoading}
                    className="text-xs px-3 py-1 rounded bg-green-600/20 text-green-300
                      hover:bg-green-600/30 transition-colors disabled:opacity-50"
                  >
                    Воскресить ({reviveCost} зол.)
                  </button>
                )}
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

// --- Merchant Room ---

const MerchantRoomContent = ({
  room,
  cfg,
  isLeader,
  interactLoading,
  onInteract,
}: {
  room: RoomView;
  cfg: Record<string, unknown>;
  isLeader: boolean;
  interactLoading: boolean;
  onInteract: (action: string, extraData?: Record<string, unknown>) => void;
}) => {
  const items = cfg.items as Array<{
    item_id: number;
    name: string;
    price: number;
    stock: number;
  }> | undefined;
  const characterGold = cfg.character_gold as number | undefined;
  const disabled = cfg.disabled === true;

  if (disabled) {
    return (
      <div className="bg-white/5 rounded-card px-4 py-3">
        <p className="text-white/40 text-sm">Торговец недоступен в этом подземелье.</p>
      </div>
    );
  }

  return (
    <div className="bg-site-blue/10 rounded-card px-4 py-4 border border-site-blue/20">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-3">
        <p className="text-site-blue text-sm font-medium">Торговец предлагает товары</p>
        {characterGold !== undefined && (
          <span className="text-yellow-300 text-xs">
            Ваше золото: {characterGold}
          </span>
        )}
      </div>

      {items && items.length > 0 ? (
        <div className="flex flex-col gap-2 max-h-64 overflow-y-auto gold-scrollbar">
          {items.map((item) => (
            <div
              key={item.item_id}
              className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 bg-white/5 rounded-card px-3 py-2"
            >
              <div className="flex-1 min-w-0">
                <p className="text-white text-sm truncate">{item.name}</p>
                <div className="flex gap-3 text-xs text-white/40 mt-0.5">
                  <span>Цена: <span className="text-yellow-300">{item.price}</span></span>
                  <span>Осталось: <span className="text-white/60">{item.stock}</span></span>
                </div>
              </div>
              {isLeader && (
                <button
                  onClick={() => onInteract('merchant_buy', { item_id: item.item_id })}
                  disabled={interactLoading || item.stock <= 0 || (characterGold !== undefined && characterGold < item.price)}
                  className="btn-blue text-xs px-3 py-1 shrink-0 disabled:opacity-50"
                >
                  {interactLoading ? '...' : 'Купить'}
                </button>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-white/40 text-sm">У торговца нет товаров.</p>
      )}

      {!isLeader && (
        <p className="text-white/30 text-xs italic mt-2">Только лидер может совершать покупки</p>
      )}
    </div>
  );
};

// --- Teleport Room ---

const TeleportRoomContent = ({ cfg }: { cfg: Record<string, unknown> }) => {
  const destination = cfg.destination_name as string | undefined;

  return (
    <div className="bg-cyan-900/20 rounded-card px-4 py-4 border border-cyan-600/20 relative overflow-hidden">
      {/* Swirl animation */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-20">
        <div className="w-24 h-24 rounded-full border-2 border-cyan-400 animate-spin-slow" />
        <div className="absolute w-16 h-16 rounded-full border border-cyan-300 animate-spin-slow" style={{ animationDirection: 'reverse' }} />
      </div>

      <div className="relative">
        <p className="text-cyan-300 text-sm font-medium mb-1">Телепорт!</p>
        <p className="text-white/50 text-xs">
          Магический портал мерцает перед вами.
        </p>
        {destination && (
          <p className="text-cyan-200 text-xs mt-2">
            Назначение: <span className="font-medium">{destination}</span>
          </p>
        )}
        <p className="text-white/30 text-xs mt-1 italic">Перемещение происходит автоматически</p>
      </div>
    </div>
  );
};

// --- Fork Room ---

const ForkRoomContent = () => (
  <div className="bg-white/5 rounded-card px-4 py-3">
    <p className="text-white/60 text-sm">
      Перед вами развилка. Выберите направление.
    </p>
  </div>
);

// --- Deadend Room ---

const DeadendRoomContent = () => (
  <div className="bg-amber-900/10 rounded-card px-4 py-3 border border-amber-800/20">
    <p className="text-amber-200/70 text-sm font-medium">Тупик</p>
    <p className="text-white/30 text-xs mt-1 italic">
      Дальше пути нет. Придётся вернуться назад.
    </p>
  </div>
);

// --- Mana Core Room ---

const ManaCoreRoomContent = ({
  room,
  isLeader,
  interactLoading,
  lastInteractResponse,
  dungeonManaCoreCh,
  onInteract,
}: {
  room: RoomView;
  isLeader: boolean;
  interactLoading: boolean;
  lastInteractResponse: InteractResponse | null;
  dungeonManaCoreCh: number;
  onInteract: (action: string) => void;
}) => {
  const mcCfg = room.room_config_visible ?? {};
  const destroyed = mcCfg.destroyed === true;
  const failed = mcCfg.failed === true;

  if (destroyed) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5 }}
        className="rounded-card px-4 py-4 border-2 border-yellow-500/60 bg-yellow-500/10"
      >
        <p className="text-yellow-300 text-base font-medium mb-2">Ядро маны уничтожено!</p>
        <p className="text-white/60 text-sm">Вы получили Кристалл подземелья.</p>
        <p className="text-site-red text-sm mt-2 font-medium animate-pulse">Подземелье рушится!</p>
        {lastInteractResponse?.loot && lastInteractResponse.loot.length > 0 && (
          <LootDisplay response={lastInteractResponse} />
        )}
      </motion.div>
    );
  }

  if (failed) {
    return (
      <div className="rounded-card px-4 py-4 border border-white/10 bg-white/5">
        <p className="text-white/50 text-sm">Ядро маны оказалось слишком сильным...</p>
        <p className="text-white/30 text-xs mt-1">Попытка уничтожить Ядро не удалась.</p>
      </div>
    );
  }

  // Active mana core
  return (
    <div className="relative rounded-card px-4 py-4 border-2 border-yellow-500/40 bg-yellow-500/5 overflow-hidden">
      {/* Glow effect */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-32 h-32 rounded-full bg-yellow-500/10 animate-pulse" />
      </div>

      <div className="relative">
        <p className="gold-text text-base font-medium mb-2">Ядро маны</p>
        <p className="text-white/60 text-sm mb-3">
          Перед вами пульсирующий кристалл, наполненный магической энергией. Это источник силы подземелья.
        </p>
        {dungeonManaCoreCh > 0 && (
          <p className="text-white/40 text-xs mb-3">
            Шанс уничтожения: <span className="text-yellow-300">{Math.round(dungeonManaCoreCh * 100)}%</span>
          </p>
        )}

        {isLeader && (
          <button
            onClick={() => onInteract('search_mana_core')}
            disabled={interactLoading}
            className="relative overflow-hidden bg-yellow-600/20 hover:bg-yellow-600/30 text-yellow-200
              text-sm px-5 py-2 rounded-card border border-yellow-500/40
              transition-colors disabled:opacity-50"
          >
            {interactLoading ? 'Попытка...' : 'Попытаться уничтожить Ядро'}
          </button>
        )}
        {!isLeader && (
          <p className="text-white/30 text-xs italic">Только лидер может попытаться уничтожить Ядро</p>
        )}
      </div>
    </div>
  );
};

// --- Loot Display ---

const LootDisplay = ({ response }: { response: InteractResponse | null }) => {
  if (!response?.loot || response.loot.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 5 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.1 }}
      className="bg-yellow-900/10 rounded-card px-3 py-3 border border-yellow-600/20 mt-2"
    >
      <p className="text-yellow-300/80 text-xs uppercase tracking-wide mb-2">Получено:</p>
      <div className="flex flex-col gap-1">
        {response.loot.map((item) => (
          <div key={item.item_id} className="flex items-center justify-between">
            <span className="text-white text-sm">{item.item_name}</span>
            <span className="text-white/40 text-sm">x{item.quantity}</span>
          </div>
        ))}
      </div>
    </motion.div>
  );
};

// --- Chest Icon (CSS-based) ---

const ChestIcon = ({ opened = false }: { opened?: boolean }) => (
  <div className="relative w-10 h-10 shrink-0">
    {/* Chest body */}
    <div className={`absolute bottom-0 w-10 h-6 rounded-sm border-2 ${
      opened ? 'border-yellow-600/40 bg-yellow-900/20' : 'border-yellow-600/60 bg-yellow-900/40'
    }`} />
    {/* Chest lid */}
    <div
      className={`absolute top-0 w-10 h-5 rounded-t-sm border-2 border-b-0 transition-transform duration-300 origin-bottom ${
        opened
          ? 'border-yellow-600/40 bg-yellow-900/20 -translate-y-1 -rotate-12'
          : 'border-yellow-600/60 bg-yellow-900/40'
      }`}
    />
    {/* Lock */}
    {!opened && (
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-yellow-500/60" />
    )}
  </div>
);

// --- Exit Row sub-component ---

export default DungeonRoom;
