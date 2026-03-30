import { useState } from 'react';
import type { DungeonRoom, DungeonCorridor } from '../../../../api/dungeons';
import { ROOM_TYPE_LABELS, ROOM_TYPE_ICONS, ROOM_COLORS } from './constants';
import type { RoomType } from './types';

// --- Local types for room_config fields ---

interface LootEntry {
  item_id: number;
  quantity: number;
  chance: number;
}

interface EventChoice {
  text: string;
  outcome_type: 'reward' | 'damage' | 'teleport' | 'heal' | 'battle' | 'nothing';
  outcome_data: string;
}

interface MerchantItem {
  item_id: number;
  price: number;
  stock: number;
}

// --- Constants ---

const STAT_CHECK_OPTIONS = [
  { value: 'strength', label: 'Сила' },
  { value: 'agility', label: 'Ловкость' },
  { value: 'intelligence', label: 'Интеллект' },
  { value: 'endurance', label: 'Выносливость' },
  { value: 'charisma', label: 'Харизма' },
  { value: 'luck', label: 'Удача' },
];

const OUTCOME_TYPES = [
  { value: 'nothing', label: 'Ничего' },
  { value: 'damage', label: 'Урон' },
  { value: 'reward', label: 'Награда' },
  { value: 'heal', label: 'Лечение' },
  { value: 'teleport', label: 'Телепорт' },
  { value: 'battle', label: 'Бой' },
];

const ROOM_TYPE_OPTIONS: { value: RoomType; label: string }[] = [
  { value: 'battle', label: 'Бой' },
  { value: 'boss', label: 'Босс' },
  { value: 'treasure', label: 'Сокровищница' },
  { value: 'trap', label: 'Ловушка' },
  { value: 'event', label: 'Событие' },
  { value: 'rest', label: 'Отдых' },
  { value: 'merchant', label: 'Торговец' },
  { value: 'fork', label: 'Развилка' },
  { value: 'teleport', label: 'Телепорт' },
  { value: 'deadend', label: 'Тупик' },
];

// --- Props ---

interface PropertyPanelProps {
  selectedRoom: DungeonRoom | null;
  selectedCorridor: DungeonCorridor | null;
  rooms: DungeonRoom[];
  onRoomChange: (room: DungeonRoom) => void;
  onCorridorChange: (corridor: DungeonCorridor) => void;
  onDeleteRoom: (roomId: number) => void;
  onDeleteCorridor: (corridorId: number) => void;
}

// --- Helpers ---

const parseMobIds = (str: string): number[] =>
  str
    .split(/[,\s]+/)
    .map((s) => parseInt(s.trim(), 10))
    .filter((n) => !isNaN(n));

const mobIdsToString = (ids: number[] | undefined): string =>
  (ids || []).join(', ');

// --- Sub-components ---

const SectionHeader = ({ children }: { children: React.ReactNode }) => (
  <h4 className="gold-text text-xs font-medium uppercase tracking-[0.06em] mt-3 mb-1">
    {children}
  </h4>
);

const FieldLabel = ({ children }: { children: React.ReactNode }) => (
  <label className="text-[11px] text-white/60 mb-0.5 block">{children}</label>
);

// --- Room Config Editors ---

const BattleConfig = ({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (c: Record<string, unknown>) => void;
}) => (
  <div className="flex flex-col gap-2">
    <FieldLabel>ID шаблонов мобов (через запятую)</FieldLabel>
    <input
      className="input-underline !text-sm"
      placeholder="1, 2, 3"
      value={mobIdsToString(config.mob_template_ids as number[])}
      onChange={(e) =>
        onChange({ ...config, mob_template_ids: parseMobIds(e.target.value) })
      }
    />
  </div>
);

const LootTable = ({
  items,
  label,
  onChange,
}: {
  items: LootEntry[];
  label: string;
  onChange: (items: LootEntry[]) => void;
}) => (
  <div className="flex flex-col gap-2">
    <div className="flex items-center justify-between">
      <FieldLabel>{label}</FieldLabel>
      <button
        type="button"
        onClick={() => onChange([...items, { item_id: 0, quantity: 1, chance: 1.0 }])}
        className="text-[10px] text-site-blue hover:text-white transition-colors"
      >
        + Добавить
      </button>
    </div>
    {items.map((row, idx) => (
      <div key={idx} className="flex flex-wrap gap-1.5 items-end bg-white/[0.03] rounded p-2">
        <div className="flex flex-col gap-0.5">
          <span className="text-[9px] text-white/40">ID предмета</span>
          <input
            type="number"
            className="input-underline !text-sm !w-16"
            value={row.item_id}
            onChange={(e) => {
              const updated = [...items];
              updated[idx] = { ...row, item_id: Number(e.target.value) };
              onChange(updated);
            }}
          />
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[9px] text-white/40">Кол-во</span>
          <input
            type="number"
            className="input-underline !text-sm !w-14"
            value={row.quantity}
            min={1}
            onChange={(e) => {
              const updated = [...items];
              updated[idx] = { ...row, quantity: Number(e.target.value) };
              onChange(updated);
            }}
          />
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[9px] text-white/40">Шанс</span>
          <input
            type="number"
            className="input-underline !text-sm !w-16"
            value={row.chance}
            step={0.05}
            min={0}
            max={1}
            onChange={(e) => {
              const updated = [...items];
              updated[idx] = { ...row, chance: Number(e.target.value) };
              onChange(updated);
            }}
          />
        </div>
        <button
          type="button"
          onClick={() => onChange(items.filter((_, i) => i !== idx))}
          className="text-site-red text-[10px] hover:text-white transition-colors ml-auto"
        >
          Удалить
        </button>
      </div>
    ))}
  </div>
);

const BossConfig = ({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (c: Record<string, unknown>) => void;
}) => (
  <div className="flex flex-col gap-3">
    <div className="flex flex-col gap-2">
      <FieldLabel>ID шаблонов мобов (через запятую)</FieldLabel>
      <input
        className="input-underline !text-sm"
        placeholder="5"
        value={mobIdsToString(config.mob_template_ids as number[])}
        onChange={(e) =>
          onChange({ ...config, mob_template_ids: parseMobIds(e.target.value) })
        }
      />
    </div>
    <LootTable
      items={(config.boss_loot as LootEntry[]) || []}
      label="Лут босса"
      onChange={(boss_loot) => onChange({ ...config, boss_loot })}
    />
  </div>
);

const TreasureConfig = ({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (c: Record<string, unknown>) => void;
}) => (
  <LootTable
    items={(config.loot_table as LootEntry[]) || []}
    label="Таблица лута"
    onChange={(loot_table) => onChange({ ...config, loot_table })}
  />
);

const TrapConfig = ({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (c: Record<string, unknown>) => void;
}) => (
  <div className="flex flex-col gap-2">
    <FieldLabel>Проверяемая характеристика</FieldLabel>
    <select
      className="input-underline !text-sm"
      value={(config.stat_check as string) || 'agility'}
      onChange={(e) => onChange({ ...config, stat_check: e.target.value })}
    >
      {STAT_CHECK_OPTIONS.map((s) => (
        <option key={s.value} value={s.value} className="bg-site-dark text-white">
          {s.label}
        </option>
      ))}
    </select>

    <div className="grid grid-cols-2 gap-2">
      <div className="flex flex-col gap-1">
        <FieldLabel>Сложность</FieldLabel>
        <input
          type="number"
          className="input-underline !text-sm"
          value={(config.difficulty as number) ?? 10}
          onChange={(e) => onChange({ ...config, difficulty: Number(e.target.value) })}
        />
      </div>
      <div className="flex flex-col gap-1">
        <FieldLabel>Урон при провале</FieldLabel>
        <input
          type="number"
          className="input-underline !text-sm"
          value={(config.fail_damage as number) ?? 20}
          onChange={(e) => onChange({ ...config, fail_damage: Number(e.target.value) })}
        />
      </div>
    </div>

    <FieldLabel>Эффект при провале</FieldLabel>
    <input
      className="input-underline !text-sm"
      placeholder="poison, stun, ..."
      value={(config.fail_effect as string) || ''}
      onChange={(e) => onChange({ ...config, fail_effect: e.target.value })}
    />
  </div>
);

// --- Outcome data editor for event choices ---

const parseOutcomeData = (raw: string): Record<string, unknown> => {
  try { return JSON.parse(raw || '{}'); } catch { return {}; }
};

const OutcomeDataFields = ({
  outcomeType,
  outcomeData,
  onChange,
}: {
  outcomeType: string;
  outcomeData: string;
  onChange: (val: string) => void;
}) => {
  const data = parseOutcomeData(outcomeData);

  const set = (key: string, value: unknown) => {
    onChange(JSON.stringify({ ...data, [key]: value }));
  };

  if (outcomeType === 'nothing') {
    return (
      <div className="flex flex-col gap-0.5 col-span-2">
        <span className="text-[9px] text-white/30 italic">Нет параметров</span>
      </div>
    );
  }

  if (outcomeType === 'damage') {
    return (
      <div className="flex flex-col gap-0.5">
        <span className="text-[9px] text-white/40">Урон</span>
        <input
          type="number"
          className="input-underline !text-sm"
          placeholder="20"
          value={(data.damage as number) ?? ''}
          onChange={(e) => set('damage', Number(e.target.value) || 0)}
        />
      </div>
    );
  }

  if (outcomeType === 'heal') {
    return (
      <div className="flex flex-col gap-0.5">
        <span className="text-[9px] text-white/40">% лечения</span>
        <input
          type="number"
          className="input-underline !text-sm"
          placeholder="30"
          value={(data.heal_percent as number) ?? ''}
          onChange={(e) => set('heal_percent', Number(e.target.value) || 0)}
        />
      </div>
    );
  }

  if (outcomeType === 'teleport') {
    return (
      <div className="flex flex-col gap-0.5">
        <span className="text-[9px] text-white/40">ID комнаты</span>
        <input
          type="number"
          className="input-underline !text-sm"
          placeholder="7"
          value={(data.target_room_id as number) ?? ''}
          onChange={(e) => set('target_room_id', Number(e.target.value) || 0)}
        />
      </div>
    );
  }

  if (outcomeType === 'battle') {
    return (
      <div className="flex flex-col gap-0.5">
        <span className="text-[9px] text-white/40">ID мобов (через запятую)</span>
        <input
          className="input-underline !text-sm"
          placeholder="1, 3, 5"
          value={((data.mob_template_ids as number[]) ?? []).join(', ')}
          onChange={(e) => set('mob_template_ids',
            e.target.value.split(',').map((s) => Number(s.trim())).filter((n) => n > 0)
          )}
        />
      </div>
    );
  }

  if (outcomeType === 'reward') {
    return (
      <div className="flex flex-col gap-1 col-span-2">
        <div className="flex gap-2">
          <div className="flex flex-col gap-0.5 flex-1">
            <span className="text-[9px] text-white/40">Золото</span>
            <input
              type="number"
              className="input-underline !text-sm"
              placeholder="100"
              value={(data.gold as number) ?? ''}
              onChange={(e) => set('gold', Number(e.target.value) || 0)}
            />
          </div>
          <div className="flex flex-col gap-0.5 flex-1">
            <span className="text-[9px] text-white/40">ID предмета</span>
            <input
              type="number"
              className="input-underline !text-sm"
              placeholder="5"
              value={((data.items as {item_id: number}[])?.[0]?.item_id) ?? ''}
              onChange={(e) => {
                const itemId = Number(e.target.value) || 0;
                const qty = ((data.items as {quantity: number}[])?.[0]?.quantity) ?? 1;
                set('items', itemId ? [{ item_id: itemId, quantity: qty }] : []);
              }}
            />
          </div>
          <div className="flex flex-col gap-0.5 w-16">
            <span className="text-[9px] text-white/40">Кол-во</span>
            <input
              type="number"
              className="input-underline !text-sm"
              placeholder="1"
              value={((data.items as {quantity: number}[])?.[0]?.quantity) ?? ''}
              onChange={(e) => {
                const qty = Number(e.target.value) || 1;
                const itemId = ((data.items as {item_id: number}[])?.[0]?.item_id) ?? 0;
                set('items', itemId ? [{ item_id: itemId, quantity: qty }] : []);
              }}
            />
          </div>
        </div>
      </div>
    );
  }

  // Fallback — raw JSON
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[9px] text-white/40">Данные (JSON)</span>
      <input
        className="input-underline !text-sm"
        placeholder="{}"
        value={outcomeData}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
};

const EventConfig = ({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (c: Record<string, unknown>) => void;
}) => {
  const choices = (config.choices as EventChoice[]) || [];

  const updateChoice = (idx: number, key: keyof EventChoice, value: string) => {
    const updated = choices.map((c, i) => (i === idx ? { ...c, [key]: value } : c));
    onChange({ ...config, choices: updated });
  };

  return (
    <div className="flex flex-col gap-2">
      <FieldLabel>Текст события</FieldLabel>
      <textarea
        className="w-full bg-transparent border border-white/10 rounded px-2 py-1.5 text-sm text-white/90 placeholder:text-white/30
                   focus:border-site-blue focus:outline-none resize-y min-h-[60px]"
        rows={3}
        placeholder="Описание события..."
        value={(config.text as string) || ''}
        onChange={(e) => onChange({ ...config, text: e.target.value })}
      />

      <div className="flex items-center justify-between mt-1">
        <FieldLabel>Варианты выбора</FieldLabel>
        <button
          type="button"
          onClick={() =>
            onChange({
              ...config,
              choices: [...choices, { text: '', outcome_type: 'nothing', outcome_data: '{}' }],
            })
          }
          className="text-[10px] text-site-blue hover:text-white transition-colors"
        >
          + Добавить
        </button>
      </div>

      {choices.map((choice, idx) => (
        <div key={idx} className="bg-white/[0.03] rounded p-2 flex flex-col gap-2">
          <span className="text-[9px] text-white/40">Вариант #{idx + 1}</span>
          <input
            className="input-underline !text-sm"
            placeholder="Текст варианта"
            value={choice.text}
            onChange={(e) => updateChoice(idx, 'text', e.target.value)}
          />
          <div className="grid grid-cols-2 gap-2">
            <div className="flex flex-col gap-0.5">
              <span className="text-[9px] text-white/40">Тип исхода</span>
              <select
                className="input-underline !text-sm"
                value={choice.outcome_type}
                onChange={(e) => updateChoice(idx, 'outcome_type', e.target.value)}
              >
                {OUTCOME_TYPES.map((o) => (
                  <option key={o.value} value={o.value} className="bg-site-dark text-white">
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <OutcomeDataFields
              outcomeType={choice.outcome_type}
              outcomeData={choice.outcome_data}
              onChange={(val) => updateChoice(idx, 'outcome_data', val)}
            />
          </div>
          <button
            type="button"
            onClick={() =>
              onChange({ ...config, choices: choices.filter((_, i) => i !== idx) })
            }
            className="text-site-red text-[10px] hover:text-white transition-colors self-end"
          >
            Удалить
          </button>
        </div>
      ))}
    </div>
  );
};

const RestConfig = ({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (c: Record<string, unknown>) => void;
}) => (
  <div className="grid grid-cols-2 gap-2">
    <div className="flex flex-col gap-1">
      <FieldLabel>Восстановление (%)</FieldLabel>
      <input
        type="number"
        className="input-underline !text-sm"
        value={(config.heal_percent as number) ?? 30}
        min={0}
        max={100}
        onChange={(e) => onChange({ ...config, heal_percent: Number(e.target.value) })}
      />
    </div>
    <div className="flex flex-col gap-1">
      <FieldLabel>Ожидание (сек)</FieldLabel>
      <input
        type="number"
        className="input-underline !text-sm"
        value={(config.wait_seconds as number) ?? 300}
        min={0}
        onChange={(e) => onChange({ ...config, wait_seconds: Number(e.target.value) })}
      />
    </div>
    <div className="flex flex-col gap-1 col-span-2">
      <FieldLabel>Стоимость (золото)</FieldLabel>
      <input
        type="number"
        className="input-underline !text-sm"
        value={(config.gold_cost as number) ?? 0}
        min={0}
        onChange={(e) => onChange({ ...config, gold_cost: Number(e.target.value) })}
      />
    </div>
  </div>
);

const MerchantConfig = ({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (c: Record<string, unknown>) => void;
}) => {
  const items = (config.items as MerchantItem[]) || [];

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <FieldLabel>Товары торговца</FieldLabel>
        <button
          type="button"
          onClick={() =>
            onChange({ ...config, items: [...items, { item_id: 0, price: 100, stock: 5 }] })
          }
          className="text-[10px] text-site-blue hover:text-white transition-colors"
        >
          + Добавить
        </button>
      </div>
      {items.map((item, idx) => (
        <div key={idx} className="flex flex-wrap gap-1.5 items-end bg-white/[0.03] rounded p-2">
          <div className="flex flex-col gap-0.5">
            <span className="text-[9px] text-white/40">ID предмета</span>
            <input
              type="number"
              className="input-underline !text-sm !w-16"
              value={item.item_id}
              onChange={(e) => {
                const updated = [...items];
                updated[idx] = { ...item, item_id: Number(e.target.value) };
                onChange({ ...config, items: updated });
              }}
            />
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-[9px] text-white/40">Цена</span>
            <input
              type="number"
              className="input-underline !text-sm !w-16"
              value={item.price}
              min={0}
              onChange={(e) => {
                const updated = [...items];
                updated[idx] = { ...item, price: Number(e.target.value) };
                onChange({ ...config, items: updated });
              }}
            />
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-[9px] text-white/40">Запас</span>
            <input
              type="number"
              className="input-underline !text-sm !w-14"
              value={item.stock}
              min={0}
              onChange={(e) => {
                const updated = [...items];
                updated[idx] = { ...item, stock: Number(e.target.value) };
                onChange({ ...config, items: updated });
              }}
            />
          </div>
          <button
            type="button"
            onClick={() =>
              onChange({ ...config, items: items.filter((_, i) => i !== idx) })
            }
            className="text-site-red text-[10px] hover:text-white transition-colors ml-auto"
          >
            Удалить
          </button>
        </div>
      ))}
    </div>
  );
};

const TeleportConfig = ({
  config,
  rooms,
  currentRoomId,
  onChange,
}: {
  config: Record<string, unknown>;
  rooms: DungeonRoom[];
  currentRoomId: number;
  onChange: (c: Record<string, unknown>) => void;
}) => (
  <div className="flex flex-col gap-1">
    <FieldLabel>Целевая комната</FieldLabel>
    <select
      className="input-underline !text-sm"
      value={(config.target_room_id as number) ?? ''}
      onChange={(e) =>
        onChange({
          ...config,
          target_room_id: e.target.value ? Number(e.target.value) : null,
        })
      }
    >
      <option value="" className="bg-site-dark text-white">
        — Выберите комнату —
      </option>
      {rooms
        .filter((r) => r.id !== currentRoomId)
        .map((r) => (
          <option key={r.id} value={r.id} className="bg-site-dark text-white">
            {r.name} ({ROOM_TYPE_LABELS[r.room_type] || r.room_type})
          </option>
        ))}
    </select>
  </div>
);

// --- Room Config Renderer ---

const RoomConfigEditor = ({
  roomType,
  config,
  rooms,
  currentRoomId,
  onChange,
}: {
  roomType: string;
  config: Record<string, unknown>;
  rooms: DungeonRoom[];
  currentRoomId: number;
  onChange: (c: Record<string, unknown>) => void;
}) => {
  switch (roomType) {
    case 'battle':
      return <BattleConfig config={config} onChange={onChange} />;
    case 'boss':
      return <BossConfig config={config} onChange={onChange} />;
    case 'treasure':
      return <TreasureConfig config={config} onChange={onChange} />;
    case 'trap':
      return <TrapConfig config={config} onChange={onChange} />;
    case 'event':
      return <EventConfig config={config} onChange={onChange} />;
    case 'rest':
      return <RestConfig config={config} onChange={onChange} />;
    case 'merchant':
      return <MerchantConfig config={config} onChange={onChange} />;
    case 'teleport':
      return (
        <TeleportConfig
          config={config}
          rooms={rooms}
          currentRoomId={currentRoomId}
          onChange={onChange}
        />
      );
    case 'fork':
    case 'deadend':
      return (
        <p className="text-white/40 text-xs">
          Для этого типа дополнительных настроек нет.
        </p>
      );
    default:
      return null;
  }
};

// --- Room Panel ---

const RoomPanel = ({
  room,
  rooms,
  onRoomChange,
  onDeleteRoom,
}: {
  room: DungeonRoom;
  rooms: DungeonRoom[];
  onRoomChange: (room: DungeonRoom) => void;
  onDeleteRoom: (roomId: number) => void;
}) => {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const update = (partial: Partial<DungeonRoom>) => {
    onRoomChange({ ...room, ...partial });
  };

  const icon = ROOM_TYPE_ICONS[room.room_type] ?? '❓';
  const color = ROOM_COLORS[room.room_type] ?? '#374151';

  return (
    <div className="flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <span
          className="w-8 h-8 flex items-center justify-center rounded text-lg shrink-0"
          style={{ backgroundColor: color }}
        >
          {icon}
        </span>
        <div className="flex flex-col min-w-0">
          <span className="text-sm text-white font-medium truncate">
            {room.name || 'Без названия'}
          </span>
          <span className="text-[10px] text-white/40">
            ID: {room.id} | {ROOM_TYPE_LABELS[room.room_type] || room.room_type}
          </span>
        </div>
      </div>

      {/* Basic fields */}
      <SectionHeader>Основные параметры</SectionHeader>

      <div className="flex flex-col gap-1">
        <FieldLabel>Тип комнаты</FieldLabel>
        <select
          className="input-underline !text-sm"
          value={room.room_type}
          onChange={(e) =>
            update({
              room_type: e.target.value as DungeonRoom['room_type'],
              room_config: {},
            })
          }
        >
          {ROOM_TYPE_OPTIONS.map((rt) => (
            <option key={rt.value} value={rt.value} className="bg-site-dark text-white">
              {rt.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <FieldLabel>Название</FieldLabel>
        <input
          className="input-underline !text-sm"
          placeholder="Зал стражей"
          value={room.name}
          onChange={(e) => update({ name: e.target.value })}
        />
      </div>

      <div className="flex flex-col gap-1">
        <FieldLabel>Описание</FieldLabel>
        <textarea
          className="w-full bg-transparent border border-white/10 rounded px-2 py-1.5 text-sm text-white/90 placeholder:text-white/30
                     focus:border-site-blue focus:outline-none resize-y min-h-[50px]"
          rows={2}
          placeholder="Тёмный зал с колоннами..."
          value={room.description}
          onChange={(e) => update({ description: e.target.value })}
        />
      </div>

      <div className="flex flex-col gap-1">
        <FieldLabel>URL изображения</FieldLabel>
        <input
          className="input-underline !text-sm"
          placeholder="https://..."
          value={room.image_url || ''}
          onChange={(e) => update({ image_url: e.target.value || null })}
        />
      </div>

      <div className="flex flex-col gap-1">
        <FieldLabel>Порядок сортировки</FieldLabel>
        <input
          type="number"
          className="input-underline !text-sm !w-24"
          value={room.sort_order}
          onChange={(e) => update({ sort_order: Number(e.target.value) })}
        />
      </div>

      {/* Flags */}
      <div className="flex flex-col gap-2 mt-1">
        <label className="flex items-center gap-2 text-xs text-white cursor-pointer">
          <input
            type="checkbox"
            checked={room.is_entrance}
            onChange={(e) => update({ is_entrance: e.target.checked })}
            className="accent-gold w-3.5 h-3.5"
          />
          Вход в подземелье
        </label>
        <label className="flex items-center gap-2 text-xs text-white cursor-pointer">
          <input
            type="checkbox"
            checked={room.is_boss_room}
            onChange={(e) => update({ is_boss_room: e.target.checked })}
            className="accent-gold w-3.5 h-3.5"
          />
          Комната босса
        </label>
        <label className="flex items-center gap-2 text-xs text-white cursor-pointer">
          <input
            type="checkbox"
            checked={room.is_mana_core_room}
            onChange={(e) => update({ is_mana_core_room: e.target.checked })}
            className="accent-gold w-3.5 h-3.5"
          />
          Комната Ядра маны
        </label>
      </div>

      {/* Type-specific config */}
      <SectionHeader>
        Настройки: {ROOM_TYPE_LABELS[room.room_type] || room.room_type}
      </SectionHeader>

      <RoomConfigEditor
        roomType={room.room_type}
        config={room.room_config || {}}
        rooms={rooms}
        currentRoomId={room.id}
        onChange={(room_config) => update({ room_config })}
      />

      {/* Delete button */}
      <div className="mt-4 pt-3 border-t border-white/10">
        {!showDeleteConfirm ? (
          <button
            type="button"
            onClick={() => setShowDeleteConfirm(true)}
            className="w-full text-sm text-site-red hover:text-white bg-site-red/10 hover:bg-site-red/30
                       rounded py-2 transition-colors duration-200"
          >
            Удалить комнату
          </button>
        ) : (
          <div className="flex flex-col gap-2">
            <p className="text-xs text-site-red text-center">
              Удалить комнату и все связанные коридоры?
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => {
                  onDeleteRoom(room.id);
                  setShowDeleteConfirm(false);
                }}
                className="flex-1 text-sm text-white bg-site-red/60 hover:bg-site-red rounded py-1.5 transition-colors"
              >
                Да, удалить
              </button>
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(false)}
                className="flex-1 text-sm text-white/60 hover:text-white bg-white/[0.06] hover:bg-white/[0.12] rounded py-1.5 transition-colors"
              >
                Отмена
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// --- Corridor Panel ---

const CorridorPanel = ({
  corridor,
  rooms,
  onCorridorChange,
  onDeleteCorridor,
}: {
  corridor: DungeonCorridor;
  rooms: DungeonRoom[];
  onCorridorChange: (corridor: DungeonCorridor) => void;
  onDeleteCorridor: (corridorId: number) => void;
}) => {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const update = (partial: Partial<DungeonCorridor>) => {
    onCorridorChange({ ...corridor, ...partial });
  };

  const fromRoom = rooms.find((r) => r.id === corridor.from_room_id);
  const toRoom = rooms.find((r) => r.id === corridor.to_room_id);
  const trapConfig = (corridor.trap_config || {}) as Record<string, unknown>;

  return (
    <div className="flex flex-col gap-3">
      {/* Header */}
      <div className="flex flex-col gap-1">
        <span className="text-sm text-white font-medium">Коридор</span>
        <span className="text-[10px] text-white/40">
          {fromRoom?.name || `#${corridor.from_room_id}`} → {toRoom?.name || `#${corridor.to_room_id}`}
        </span>
      </div>

      <SectionHeader>Основные параметры</SectionHeader>

      <div className="flex flex-col gap-1">
        <FieldLabel>Стоимость стамины</FieldLabel>
        <input
          type="number"
          className="input-underline !text-sm !w-24"
          value={corridor.stamina_cost}
          min={0}
          onChange={(e) => update({ stamina_cost: Number(e.target.value) })}
        />
      </div>

      <label className="flex items-center gap-2 text-xs text-white cursor-pointer">
        <input
          type="checkbox"
          checked={corridor.is_bidirectional}
          onChange={(e) => update({ is_bidirectional: e.target.checked })}
          className="accent-gold w-3.5 h-3.5"
        />
        Двунаправленный
      </label>

      <div className="flex flex-col gap-1">
        <FieldLabel>Описание</FieldLabel>
        <input
          className="input-underline !text-sm"
          placeholder="Узкий тёмный коридор"
          value={corridor.description || ''}
          onChange={(e) => update({ description: e.target.value || null })}
        />
      </div>

      {/* Random battle */}
      <SectionHeader>Случайный бой</SectionHeader>

      <div className="flex flex-col gap-1">
        <FieldLabel>Шанс боя (0 — 1)</FieldLabel>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={corridor.random_battle_chance}
          onChange={(e) => update({ random_battle_chance: Number(e.target.value) })}
          className="w-full accent-site-blue"
        />
        <span className="text-[10px] text-white/50 text-right">
          {Math.round(corridor.random_battle_chance * 100)}%
        </span>
      </div>

      {corridor.random_battle_chance > 0 && (
        <div className="flex flex-col gap-1">
          <FieldLabel>ID мобов (через запятую)</FieldLabel>
          <input
            className="input-underline !text-sm"
            placeholder="1, 2, 3"
            value={mobIdsToString(corridor.random_battle_mob_ids ?? undefined)}
            onChange={(e) => {
              const ids = parseMobIds(e.target.value);
              update({ random_battle_mob_ids: ids.length > 0 ? ids : null });
            }}
          />
        </div>
      )}

      {/* Trap */}
      <SectionHeader>Ловушка</SectionHeader>

      <div className="flex flex-col gap-1">
        <FieldLabel>Шанс ловушки (0 — 1)</FieldLabel>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={corridor.trap_chance}
          onChange={(e) => update({ trap_chance: Number(e.target.value) })}
          className="w-full accent-site-blue"
        />
        <span className="text-[10px] text-white/50 text-right">
          {Math.round(corridor.trap_chance * 100)}%
        </span>
      </div>

      {corridor.trap_chance > 0 && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-1">
            <FieldLabel>Характеристика</FieldLabel>
            <select
              className="input-underline !text-sm"
              value={(trapConfig.stat_check as string) || 'agility'}
              onChange={(e) =>
                update({
                  trap_config: { ...trapConfig, stat_check: e.target.value },
                })
              }
            >
              {STAT_CHECK_OPTIONS.map((s) => (
                <option key={s.value} value={s.value} className="bg-site-dark text-white">
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="flex flex-col gap-1">
              <FieldLabel>Сложность</FieldLabel>
              <input
                type="number"
                className="input-underline !text-sm"
                value={(trapConfig.difficulty as number) ?? 10}
                onChange={(e) =>
                  update({
                    trap_config: { ...trapConfig, difficulty: Number(e.target.value) },
                  })
                }
              />
            </div>
            <div className="flex flex-col gap-1">
              <FieldLabel>Урон при провале</FieldLabel>
              <input
                type="number"
                className="input-underline !text-sm"
                value={(trapConfig.fail_damage as number) ?? 15}
                onChange={(e) =>
                  update({
                    trap_config: { ...trapConfig, fail_damage: Number(e.target.value) },
                  })
                }
              />
            </div>
          </div>
        </div>
      )}

      {/* Delete button */}
      <div className="mt-4 pt-3 border-t border-white/10">
        {!showDeleteConfirm ? (
          <button
            type="button"
            onClick={() => setShowDeleteConfirm(true)}
            className="w-full text-sm text-site-red hover:text-white bg-site-red/10 hover:bg-site-red/30
                       rounded py-2 transition-colors duration-200"
          >
            Удалить коридор
          </button>
        ) : (
          <div className="flex flex-col gap-2">
            <p className="text-xs text-site-red text-center">Удалить этот коридор?</p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => {
                  onDeleteCorridor(corridor.id);
                  setShowDeleteConfirm(false);
                }}
                className="flex-1 text-sm text-white bg-site-red/60 hover:bg-site-red rounded py-1.5 transition-colors"
              >
                Да, удалить
              </button>
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(false)}
                className="flex-1 text-sm text-white/60 hover:text-white bg-white/[0.06] hover:bg-white/[0.12] rounded py-1.5 transition-colors"
              >
                Отмена
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// --- Main PropertyPanel ---

const PropertyPanel = ({
  selectedRoom,
  selectedCorridor,
  rooms,
  onRoomChange,
  onCorridorChange,
  onDeleteRoom,
  onDeleteCorridor,
}: PropertyPanelProps) => {
  return (
    <div className="gray-bg flex flex-col p-3 rounded-lg h-full overflow-y-auto">
      <h3 className="gold-text text-sm font-medium uppercase tracking-[0.06em] mb-3 px-1">
        Свойства
      </h3>

      {selectedRoom ? (
        <RoomPanel
          room={selectedRoom}
          rooms={rooms}
          onRoomChange={onRoomChange}
          onDeleteRoom={onDeleteRoom}
        />
      ) : selectedCorridor ? (
        <CorridorPanel
          corridor={selectedCorridor}
          rooms={rooms}
          onCorridorChange={onCorridorChange}
          onDeleteCorridor={onDeleteCorridor}
        />
      ) : (
        <div className="flex flex-col items-center justify-center flex-1 py-12 text-center">
          <span className="text-3xl mb-3 opacity-30">🖱️</span>
          <p className="text-sm text-white/40">
            Выберите комнату или коридор для редактирования
          </p>
        </div>
      )}
    </div>
  );
};

export default PropertyPanel;
