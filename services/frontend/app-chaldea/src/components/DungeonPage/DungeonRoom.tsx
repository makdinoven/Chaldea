import { useState, useCallback, useEffect } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  interactRoom,
  selectInteractLoading,
  selectLastInteractResponse,
  clearInteractResponse,
} from '../../redux/slices/dungeonSlice';
import useCountdown from '../../hooks/useCountdown';
import { fetchItemsBulk } from '../../api/bulk';
import type {
  RoomView,
  InteractAction,
  InteractResponse,
  SessionMember,
  SessionState,
  LootEntry,
} from '../../api/dungeons';

// --- Types ---

type OnInteract = (action: InteractAction, extraData?: Record<string, unknown>) => void;

interface DungeonRoomProps {
  room: RoomView;
  session: SessionState;
  characterId: number;
  isLeader: boolean;
  onGoToBattle: () => void;
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
};

const LEADER_ONLY_HINT = 'Решения принимает лидер группы';

// --- Component ---

const DungeonRoom = ({ room, session, characterId, isLeader, onGoToBattle }: DungeonRoomProps) => {
  const dispatch = useAppDispatch();
  const interactLoading = useAppSelector(selectInteractLoading);
  const lastInteractResponse = useAppSelector(selectLastInteractResponse);

  const badge = ROOM_TYPE_BADGES[room.room_type] ?? { label: room.room_type, color: 'bg-white/10 text-white/70' };

  // Interaction results belong to the room they happened in.
  useEffect(() => {
    dispatch(clearInteractResponse());
  }, [dispatch, room.id]);

  const handleInteract = useCallback<OnInteract>(
    (action, extraData) => {
      dispatch(interactRoom({ sessionId: session.session_id, characterId, action, extraData }));
    },
    [dispatch, session.session_id, characterId],
  );

  const ctx: RoomCtx = {
    room,
    cfg: room.room_config_visible ?? {},
    session,
    isLeader,
    busy: interactLoading,
    last: lastInteractResponse,
    onInteract: handleInteract,
    onGoToBattle,
  };

  return (
    <motion.div
      key={room.id}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="bg-black/40 rounded-card p-4 sm:p-6 backdrop-blur-sm flex flex-col gap-4"
    >
      {/* Room header */}
      {/* Title above its tags: the panel can be narrow even on a wide screen. */}
      <div className="flex flex-col gap-2">
        <h2 className="gold-text text-lg sm:text-xl font-medium min-w-0 break-words">
          {room.name}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          {room.is_entrance && (
            <span className="text-[10px] sm:text-xs px-2 py-0.5 rounded-full font-medium bg-white/10 text-white/70">
              Вход
            </span>
          )}
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

      {room.image_url && (
        <div className="rounded-card overflow-hidden max-h-48">
          <img src={room.image_url} alt={room.name} className="w-full h-full object-cover" />
        </div>
      )}

      {room.description && (
        <p className="text-white/70 text-sm leading-relaxed whitespace-pre-line">{room.description}</p>
      )}

      {room.is_mana_core_room ? <ManaCoreRoomContent {...ctx} /> : <RoomContent {...ctx} />}

      {!!ctx.cfg.lever && <LeverContent {...ctx} />}

      <LootDisplay response={lastInteractResponse} />

      {!isLeader && (
        <p className="text-white/30 text-xs italic">{LEADER_ONLY_HINT}</p>
      )}

      {room.exits.length === 0 && (
        <p className="text-white/40 text-sm italic">Нет доступных выходов</p>
      )}
    </motion.div>
  );
};

// --- Shared context of the room sub-components ---

interface RoomCtx {
  room: RoomView;
  cfg: Record<string, unknown>;
  session: SessionState;
  isLeader: boolean;
  busy: boolean;
  last: InteractResponse | null;
  onInteract: OnInteract;
  onGoToBattle: () => void;
}

const RoomContent = (ctx: RoomCtx) => {
  switch (ctx.room.room_type) {
    case 'battle':
      return <BattleRoomContent {...ctx} isBoss={false} />;
    case 'boss':
      return <BossRoomContent {...ctx} />;
    case 'treasure':
      return <TreasureRoomContent {...ctx} />;
    case 'trap':
      return <TrapRoomContent {...ctx} />;
    case 'event':
      return <EventRoomContent {...ctx} />;
    case 'rest':
      return <RestRoomContent {...ctx} />;
    case 'merchant':
      return <MerchantRoomContent {...ctx} />;
    case 'teleport':
      return <TeleportRoomContent {...ctx} />;
    case 'fork':
      return <PlainNote text="Перед вами развилка. Выберите направление на карте." />;
    case 'deadend':
      return <PlainNote text="Тупик. Дальше пути нет — придётся вернуться." />;
    default:
      return null;
  }
};

const PlainNote = ({ text }: { text: string }) => (
  <div className="bg-white/5 rounded-card px-4 py-3">
    <p className="text-white/60 text-sm">{text}</p>
  </div>
);

const ClearedNote = ({ text }: { text: string }) => (
  <div className="bg-green-900/20 rounded-card px-4 py-3 border border-green-600/20 flex items-center gap-2">
    <span className="text-green-400 text-base">&#10003;</span>
    <p className="text-green-300 text-sm font-medium">{text}</p>
  </div>
);

// --- Battle / Boss ---

const BattleRoomContent = ({ room, session, isLeader, busy, onInteract, onGoToBattle, isBoss }: RoomCtx & { isBoss: boolean }) => {
  if (room.is_cleared) {
    return <ClearedNote text={isBoss ? 'Босс повержен!' : 'Комната зачищена'} />;
  }

  if (session.phase === 'in_battle') {
    return (
      <div className="bg-red-900/20 rounded-card px-4 py-3 border border-red-600/20 flex flex-col sm:flex-row sm:items-center gap-2">
        <p className="text-yellow-300 text-sm font-medium flex-1">Бой идёт!</p>
        {session.active_battle_id && (
          <button onClick={onGoToBattle} className="btn-blue text-xs px-4 py-1.5 self-start sm:self-auto">
            Перейти к бою
          </button>
        )}
      </div>
    );
  }

  // battle_pending (the battle did not start / was aborted) — or an uncleared room
  return (
    <div className={`rounded-card px-4 py-3 border flex flex-col gap-2 ${isBoss ? 'bg-red-950/30 border-red-700/30' : 'bg-red-900/20 border-red-600/20'}`}>
      <p className={`text-sm font-medium ${isBoss ? 'text-red-200' : 'text-red-300'}`}>
        {isBoss ? 'Здесь обитает могущественный враг!' : 'Путь преграждают враги!'}
      </p>
      <p className="text-white/50 text-xs">
        Начните бой или отступите в уже исследованную комнату.
      </p>
      {isLeader && (
        <button
          onClick={() => onInteract('start_battle')}
          disabled={busy}
          className="btn-blue text-xs px-4 py-1.5 self-start disabled:opacity-50"
        >
          {busy ? 'Начинаем...' : 'Начать бой'}
        </button>
      )}
    </div>
  );
};

const BossRoomContent = (ctx: RoomCtx) => {
  const { room, cfg, session, isLeader, busy, onInteract } = ctx;
  if (!room.is_cleared) {
    return <BattleRoomContent {...ctx} isBoss />;
  }
  const lootCollected = cfg.loot_collected === true;
  const manaCore = session.mana_core;

  return (
    <div className="flex flex-col gap-3">
      <ClearedNote text="Босс повержен!" />

      {/* Mana core: revealed for this run only, searchable before the chest */}
      {manaCore?.revealed && manaCore.accessible && !lootCollected && (
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
          className="bg-gold/5 rounded-card px-4 py-4 border border-gold/40 flex flex-col gap-2"
        >
          <p className="gold-text text-sm font-medium uppercase">Найден путь к ядру маны</p>
          <p className="text-white/60 text-xs">
            За поверженным боссом открылся проход{manaCore.room_name ? ` в «${manaCore.room_name}»` : ''}.
            Спуститься туда можно до того, как вы откроете сундук. Уничтоженное ядро погасит подземелье навсегда.
          </p>
          {isLeader && (
            <button
              onClick={() => onInteract('enter_mana_core')}
              disabled={busy}
              className="btn-blue text-xs px-4 py-1.5 self-start disabled:opacity-50"
            >
              {busy ? 'Спускаемся...' : 'Спуститься к ядру маны'}
            </button>
          )}
        </motion.div>
      )}
      {manaCore?.searched && (
        <p className="text-white/40 text-xs">
          {manaCore.destroyed ? 'Ядро маны уничтожено — подземелье угасает.' : 'Ядро маны ускользнуло.'}
        </p>
      )}

      {!lootCollected ? (
        isLeader ? (
          <button
            onClick={() => onInteract('open_chest')}
            disabled={busy}
            className="bg-yellow-900/20 rounded-card px-4 py-4 border border-yellow-600/30 text-left hover:bg-yellow-900/30 transition-colors disabled:opacity-50"
          >
            <div className="flex items-center gap-3">
              <ChestIcon />
              <div>
                <p className="text-yellow-300 text-sm font-medium">
                  {busy ? 'Открываем...' : 'Открыть сундук босса'}
                </p>
                <p className="text-white/40 text-xs mt-0.5">
                  Забег будет пройден, после чего добычу можно поделить. Подземелье уйдёт на откат.
                </p>
              </div>
            </div>
          </button>
        ) : (
          <PlainNote text="Сундук босса ждёт, когда его откроет лидер." />
        )
      ) : (
        <PlainNote text="Сундук босса открыт." />
      )}
    </div>
  );
};

// --- Treasure ---

const TreasureRoomContent = ({ cfg, isLeader, busy, onInteract }: RoomCtx) => {
  if (cfg.loot_collected === true) {
    return (
      <div className="bg-white/5 rounded-card px-4 py-3 flex items-center gap-3">
        <ChestIcon opened />
        <p className="text-white/40 text-sm">Сундук уже открыт</p>
      </div>
    );
  }
  return (
    <div className="bg-yellow-900/20 rounded-card px-4 py-4 border border-yellow-600/20 flex items-center gap-3">
      <ChestIcon />
      <div className="flex-1">
        <p className="text-yellow-300 text-sm font-medium">Вы видите сундук с сокровищами!</p>
        {isLeader && (
          <button
            onClick={() => onInteract('open_chest')}
            disabled={busy}
            className="btn-blue text-xs px-4 py-1.5 mt-2 disabled:opacity-50"
          >
            {busy ? 'Открываем...' : 'Открыть сундук'}
          </button>
        )}
      </div>
    </div>
  );
};

// --- Trap ---

const TrapRoomContent = ({ cfg }: RoomCtx) => {
  const result = cfg.trap_result as { passed?: boolean; damage?: number } | undefined;
  if (!result) {
    return <PlainNote text="Вы чувствуете опасность... Ловушка срабатывает при входе." />;
  }
  return (
    <div className={`rounded-card px-4 py-3 border ${result.passed ? 'bg-green-900/20 border-green-600/20' : 'bg-orange-900/20 border-orange-600/20'}`}>
      <p className={`text-sm font-medium ${result.passed ? 'text-green-300' : 'text-orange-300'}`}>
        {result.passed ? 'Ловушка обезврежена' : 'Ловушка сработала'}
      </p>
      {!result.passed && !!result.damage && (
        <p className="text-white/50 text-xs mt-1">Урон каждому: {result.damage}</p>
      )}
    </div>
  );
};

// --- Event ---

const EventRoomContent = ({ cfg, isLeader, busy, last, onInteract }: RoomCtx) => {
  const text = cfg.text as string | undefined;
  const choices = (cfg.choices as string[] | undefined) ?? [];
  // Read by a mage (FEAT-176): what each choice leads to, roughly.
  const hints = (cfg.choice_hints as string[] | undefined) ?? [];
  const choiceMade = cfg.choice_made as number | undefined;

  return (
    <div className="bg-purple-900/20 rounded-card px-4 py-4 border border-purple-600/20 flex flex-col gap-3">
      {text && (
        <p className="text-purple-200/90 text-sm italic leading-relaxed border-l-2 border-purple-500/30 pl-3 whitespace-pre-line">
          {text}
        </p>
      )}

      {choiceMade !== undefined ? (
        <div className="bg-purple-800/20 rounded-card px-3 py-2">
          <p className="text-white/40 text-xs mb-1">Сделанный выбор:</p>
          <p className="text-purple-300 text-sm font-medium">{choices[choiceMade] ?? `Вариант ${choiceMade + 1}`}</p>
          {last?.action === 'event_choice' && last.message && (
            <p className="text-white/60 text-sm mt-2">{last.message}</p>
          )}
        </div>
      ) : choices.length === 0 ? (
        <p className="text-white/40 text-xs italic">
          У этого события нет вариантов выбора. Можно идти дальше.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="text-white/40 text-xs uppercase tracking-wide">Выберите действие:</p>
          {choices.map((choice, idx) => (
            <button
              key={idx}
              onClick={() => onInteract('event_choice', { choice_index: idx })}
              disabled={busy || !isLeader}
              className="text-left bg-purple-800/20 hover:bg-purple-800/40 rounded-card px-4 py-3 border border-purple-500/20 hover:border-purple-500/40 text-purple-200 text-sm transition-colors disabled:opacity-50"
            >
              {choice || `Вариант ${idx + 1}`}
              {hints[idx] && (
                <span
                  className={`ml-2 inline-block rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide align-middle ${
                    HINT_TONE[hints[idx]] ?? 'bg-white/10 text-white/60'
                  }`}
                >
                  {hints[idx]}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

// --- Rest ---

const formatWait = (seconds: number): string =>
  seconds >= 60 ? `${Math.round(seconds / 60)} мин.` : `${seconds} сек.`;

const RestRoomContent = ({ cfg, session, isLeader, busy, onInteract }: RoomCtx) => {
  const healPercent = (cfg.heal_percent as number | undefined) ?? 30;
  const waitSeconds = (cfg.wait_seconds as number | undefined) ?? 60;
  const goldCost = (cfg.gold_cost as number | undefined) ?? 0;
  const reviveCost = (cfg.revive_gold_cost as number | undefined) ?? 500;
  const restUsed = cfg.rest_used === true;
  const restStartedAt = cfg.rest_started_at as number | undefined; // unix seconds

  const restEnd = restStartedAt ? Math.ceil(restStartedAt + waitSeconds) : null;
  const { formatted, isDone } = useCountdown(restEnd);
  const deadMembers = session.members.filter((m) => m.status === 'dead');

  let body;
  if (restUsed) {
    body = <p className="text-green-300 text-sm font-medium">Отдых здесь уже использован.</p>;
  } else if (restStartedAt && !isDone) {
    body = (
      <div className="flex items-center gap-3">
        <div className="w-14 h-14 rounded-full border-2 border-green-500/40 flex items-center justify-center shrink-0">
          <span className="text-green-300 text-sm font-mono font-medium">{formatted}</span>
        </div>
        <p className="text-white/50 text-xs">Группа отдыхает. Осталось до конца привала.</p>
      </div>
    );
  } else if (restStartedAt && isDone) {
    body = (
      <div className="flex flex-col gap-2">
        <p className="text-green-300 text-sm font-medium">Привал окончен!</p>
        {isLeader && (
          <button
            onClick={() => onInteract('complete_rest')}
            disabled={busy}
            className="btn-blue text-xs px-4 py-1.5 self-start disabled:opacity-50"
          >
            {busy ? 'Завершаем...' : `Завершить отдых (+${healPercent}% HP)`}
          </button>
        )}
      </div>
    );
  } else {
    body = (
      <div className="flex flex-col gap-3">
        <p className="text-green-300 text-sm font-medium">Место отдыха. Можно восстановить силы.</p>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-white/50">
          <span>Лечение: <span className="text-green-300">{healPercent}% HP</span></span>
          <span>Ожидание: <span className="text-green-300">{formatWait(waitSeconds)}</span></span>
          {goldCost > 0 && <span>Стоимость: <span className="text-gold">{goldCost} золота</span></span>}
        </div>
        {isLeader && (
          <button
            onClick={() => onInteract('start_rest')}
            disabled={busy}
            className="btn-blue text-xs px-4 py-1.5 self-start disabled:opacity-50"
          >
            {busy ? 'Устраиваемся...' : 'Устроить привал'}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="bg-green-900/20 rounded-card px-4 py-4 border border-green-600/20">
      {body}
      {deadMembers.length > 0 && (
        <ReviveSection
          deadMembers={deadMembers}
          reviveCost={reviveCost}
          isLeader={isLeader}
          busy={busy}
          onInteract={onInteract}
        />
      )}
    </div>
  );
};

const ReviveSection = ({
  deadMembers,
  reviveCost,
  isLeader,
  busy,
  onInteract,
}: {
  deadMembers: SessionMember[];
  reviveCost: number;
  isLeader: boolean;
  busy: boolean;
  onInteract: OnInteract;
}) => {
  const [confirmId, setConfirmId] = useState<number | null>(null);

  return (
    <div className="mt-4 pt-3 border-t border-green-600/20">
      <p className="text-white/50 text-xs uppercase tracking-wide mb-2">Павшие союзники</p>
      <div className="flex flex-col gap-2">
        {deadMembers.map((member) => (
          <div key={member.character_id} className="flex flex-wrap items-center justify-between gap-2 bg-red-900/10 rounded-card px-3 py-2">
            <span className="text-white/60 text-sm">{member.name}</span>
            {isLeader && (confirmId === member.character_id ? (
              <div className="flex items-center gap-2">
                <span className="text-gold text-xs">{reviveCost} золота?</span>
                <button
                  onClick={() => {
                    onInteract('revive_member', { target_character_id: member.character_id });
                    setConfirmId(null);
                  }}
                  disabled={busy}
                  className="text-xs px-3 py-1.5 rounded-card bg-green-600/20 text-green-300 hover:bg-green-600/30 transition-colors disabled:opacity-50"
                >
                  Да
                </button>
                <button
                  onClick={() => setConfirmId(null)}
                  className="text-xs px-3 py-1.5 rounded-card bg-white/5 text-white/50 hover:bg-white/10 transition-colors"
                >
                  Нет
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmId(member.character_id)}
                disabled={busy}
                className="text-xs px-3 py-1.5 rounded-card bg-green-600/20 text-green-300 hover:bg-green-600/30 transition-colors disabled:opacity-50"
              >
                Воскресить ({reviveCost} зол.)
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
};

// --- Merchant ---

interface MerchantItem {
  item_id: number;
  price?: number;
  stock?: number;
}

const MerchantRoomContent = ({ cfg, isLeader, busy, onInteract }: RoomCtx) => {
  const items = ((cfg.items as MerchantItem[] | undefined) ?? []).filter((i) => i && i.item_id);
  const [names, setNames] = useState<Record<number, string>>({});
  const idsKey = items.map((i) => i.item_id).join(',');

  useEffect(() => {
    const ids = idsKey ? idsKey.split(',').map(Number) : [];
    if (ids.length === 0) return;
    let cancelled = false;
    fetchItemsBulk(ids)
      .then((rows) => {
        if (cancelled) return;
        setNames(Object.fromEntries(rows.map((r) => [r.id, r.name])));
      })
      .catch((e: unknown) => {
        if (!cancelled) toast.error(e instanceof Error ? e.message : 'Не удалось загрузить товары торговца');
      });
    return () => {
      cancelled = true;
    };
  }, [idsKey]);

  return (
    <div className="bg-site-blue/10 rounded-card px-4 py-4 border border-site-blue/20">
      <p className="text-site-blue text-sm font-medium mb-3">Торговец предлагает товары</p>
      {items.length === 0 ? (
        <p className="text-white/40 text-sm">У торговца нет товаров.</p>
      ) : (
        <div className="flex flex-col gap-2 max-h-64 overflow-y-auto gold-scrollbar">
          {items.map((item) => {
            const stock = item.stock ?? null;
            return (
              <div key={item.item_id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 bg-white/5 rounded-card px-3 py-2">
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm break-words">{names[item.item_id] ?? `Предмет #${item.item_id}`}</p>
                  <div className="flex gap-3 text-xs text-white/40 mt-0.5">
                    <span>Цена: <span className="text-gold">{item.price ?? 0}</span></span>
                    {stock !== null && <span>Осталось: <span className="text-white/60">{stock}</span></span>}
                  </div>
                </div>
                {isLeader && (
                  <button
                    onClick={() => onInteract('merchant_buy', { item_id: item.item_id, quantity: 1 })}
                    disabled={busy || (stock !== null && stock <= 0)}
                    className="btn-blue text-xs px-3 py-1.5 shrink-0 self-start sm:self-auto disabled:opacity-50"
                  >
                    Купить
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
      <p className="text-white/30 text-xs mt-2">Покупки оплачивает лидер и кладёт в общий инвентарь.</p>
    </div>
  );
};

// --- Teleport ---

const TeleportRoomContent = (ctx: RoomCtx) =>
  ctx.cfg.portal === 'red' ? <RedPortalContent {...ctx} /> : <BluePortalContent {...ctx} />;

/** How a mage's read of an event choice is coloured: good, bad, neither. */
const HINT_TONE: Record<string, string> = {
  награда: 'bg-gold/20 text-gold',
  исцеление: 'bg-green-500/20 text-green-300',
  ключ: 'bg-gold/20 text-gold',
  опасно: 'bg-site-red/20 text-site-red',
  бой: 'bg-site-red/20 text-site-red',
};

/** What kind of room a read portal leads to, for the line under it. */
const PORTAL_ROOM_KIND: Record<string, string> = {
  battle: 'бой', boss: 'логово босса', treasure: 'сокровищница', trap: 'комната-ловушка', event: 'событие',
  rest: 'привал', merchant: 'торговец', teleport: 'портал', fork: 'развилка', deadend: 'тупик',
};

const BluePortalContent = ({ cfg, session, isLeader, busy, onInteract }: RoomCtx) => {
  const read = cfg.portal_to as { name: string; room_type: string } | undefined;
  const targetId = typeof cfg.target_room_id === 'number' ? cfg.target_room_id : null;
  const known = session.explored_rooms.find((r) => r.id === targetId);
  return (
    <div className="bg-cyan-900/20 rounded-card px-4 py-4 border border-cyan-600/20 flex flex-col gap-2">
      <p className="text-cyan-300 text-sm font-medium">Синий портал</p>
      <p className="text-white/60 text-sm">
        Портал ровно мерцает и ждёт. Шагнуть в него можно когда угодно, а можно просто пройти мимо.
      </p>
      {targetId === null ? (
        <p className="text-white/40 text-xs">Портал никуда не ведёт.</p>
      ) : (
        <>
          <p className="text-white/50 text-xs">
            Ведёт{' '}
            {read ? (
              <>
                в «{read.name}» <span className="text-cyan-200/80">({PORTAL_ROOM_KIND[read.room_type] ?? 'комната'})</span>
              </>
            ) : known ? (
              <>в «{known.name}»</>
            ) : (
              'в неизведанную комнату'
            )}
          </p>
          {isLeader ? (
            <button
              onClick={() => onInteract('use_portal')}
              disabled={busy}
              className="self-start bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-100 text-sm px-5 py-2 rounded-card border border-cyan-500/40 transition-colors disabled:opacity-50"
            >
              {busy ? 'Переход...' : 'Шагнуть в портал'}
            </button>
          ) : (
            <p className="text-white/40 text-xs">Шагнуть в портал решает лидер группы.</p>
          )}
        </>
      )}
    </div>
  );
};

const RedPortalContent = ({ cfg }: RoomCtx) => {
  const result = cfg.portal_result as { passed?: boolean } | undefined;
  if (result?.passed) {
    return (
      <div className="bg-green-900/20 rounded-card px-4 py-3 border border-green-600/20">
        <p className="text-green-300 text-sm font-medium">Красный портал распознан</p>
        <p className="text-white/50 text-xs mt-1">Ловушка раскрыта — портал больше никого не затянет.</p>
      </div>
    );
  }
  return (
    <div className="bg-red-900/20 rounded-card px-4 py-3 border border-red-600/30">
      <p className="text-red-300 text-sm font-medium">Красный портал</p>
      <p className="text-white/50 text-xs mt-1">
        Багровое марево дрожит над полом. Тот, кто войдёт сюда и не разгадает ловушку, будет выброшен неизвестно
        куда.
      </p>
    </div>
  );
};

// --- Lever (any room) ---

const LeverContent = ({ cfg, isLeader, busy, onInteract }: RoomCtx) => {
  const pulled = (cfg.lever as { pulled?: boolean } | undefined)?.pulled === true;
  return (
    <div className="bg-white/5 rounded-card px-4 py-3 border border-white/10 flex flex-col gap-2">
      <p className="text-white/80 text-sm font-medium">Рычаг</p>
      <p className="text-white/50 text-xs">
        {pulled
          ? 'Рычаг опущен — где-то в подземелье открылся проход.'
          : 'Из стены торчит ржавый рычаг. Похоже, он что-то открывает.'}
      </p>
      {!pulled && isLeader && (
        <button
          onClick={() => onInteract('pull_lever')}
          disabled={busy}
          className="self-start bg-white/10 hover:bg-white/15 text-white/90 text-sm px-5 py-2 rounded-card border border-white/20 transition-colors disabled:opacity-50"
        >
          {busy ? 'Тянем...' : 'Опустить рычаг'}
        </button>
      )}
    </div>
  );
};

// --- Mana core room ---

const ManaCoreRoomContent = ({ session, isLeader, busy, onInteract }: RoomCtx) => {
  const core = session.mana_core;
  if (core?.searched) {
    return (
      <div className={`rounded-card px-4 py-4 border ${core.destroyed ? 'border-gold/50 bg-gold/10' : 'border-white/10 bg-white/5'}`}>
        <p className={`text-sm font-medium ${core.destroyed ? 'gold-text' : 'text-white/60'}`}>
          {core.destroyed ? 'Ядро маны уничтожено' : 'Ядро маны ускользнуло'}
        </p>
      </div>
    );
  }
  return (
    <div className="relative rounded-card px-4 py-4 border border-gold/40 bg-gold/5 overflow-hidden">
      <p className="gold-text text-base font-medium mb-2">Ядро маны</p>
      <p className="text-white/60 text-sm mb-3">
        Пульсирующий кристалл — источник силы подземелья. Если его уничтожить, группа получит Кристалл
        подземелья, а само подземелье угаснет навсегда.
      </p>
      {isLeader && (
        <button
          onClick={() => onInteract('search_mana_core')}
          disabled={busy}
          className="bg-yellow-600/20 hover:bg-yellow-600/30 text-yellow-200 text-sm px-5 py-2 rounded-card border border-yellow-500/40 transition-colors disabled:opacity-50"
        >
          {busy ? 'Ищем...' : 'Искать ядро'}
        </button>
      )}
    </div>
  );
};

// --- Loot of the last action ---

const lootLine = (entry: LootEntry): string => {
  if (entry.gold) return `${entry.gold} золота (лидеру)`;
  return `${entry.item_name || `Предмет #${entry.item_id}`} ×${entry.quantity ?? 1}`;
};

const LootDisplay = ({ response }: { response: InteractResponse | null }) => {
  const loot = response?.loot_gained ?? [];
  if (loot.length === 0) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 5 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.1 }}
      className="bg-yellow-900/10 rounded-card px-3 py-3 border border-yellow-600/20"
    >
      <p className="text-yellow-300/80 text-xs uppercase tracking-wide mb-2">Получено:</p>
      <div className="flex flex-col gap-1">
        {loot.map((entry, i) => (
          <span key={i} className="text-white text-sm">{lootLine(entry)}</span>
        ))}
      </div>
    </motion.div>
  );
};

// --- Chest Icon ---

const ChestIcon = ({ opened = false }: { opened?: boolean }) => (
  <div className="relative w-10 h-10 shrink-0">
    <div className={`absolute bottom-0 w-10 h-6 rounded-sm border-2 ${
      opened ? 'border-yellow-600/40 bg-yellow-900/20' : 'border-yellow-600/60 bg-yellow-900/40'
    }`} />
    <div
      className={`absolute top-0 w-10 h-5 rounded-t-sm border-2 border-b-0 transition-transform duration-300 origin-bottom ${
        opened
          ? 'border-yellow-600/40 bg-yellow-900/20 -translate-y-1 -rotate-12'
          : 'border-yellow-600/60 bg-yellow-900/40'
      }`}
    />
    {!opened && (
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-yellow-500/60" />
    )}
  </div>
);

export default DungeonRoom;
