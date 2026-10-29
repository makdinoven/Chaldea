import { useState } from 'react';
import type { DungeonRoom, DungeonCorridor } from '../../../../api/dungeons';
import { ROOM_TYPE_LABELS, ROOM_TYPE_ICONS, ROOM_COLORS } from './constants';
import type { RoomType } from './types';
import { FOOTPRINT } from '../../../DungeonBoard3D/dioramaLayout';
import { boardTypeOf } from '../../../DungeonBoard3D/editorToBoard';
import {
  DUNGEON_KEYS,
  DUNGEON_KEY_KINDS,
} from '../../../DungeonPage/dungeonConstants';
import { EntityListPicker, EntityPicker } from './pickers';
import { useCurrency } from '../../../../hooks/useCurrency';
import { getCurrencyForms } from '../../../../utils/currency';

const GRID_MIN = 2;
const GRID_MAX = 8;

const GRID_KEYS = ['grid_w', 'grid_d'] as const;

/** One side of a room's footprint on the 3D miniature; empty falls back to its kind's size. */
const SizeInput = ({
  room,
  axis,
  onChange,
}: {
  room: DungeonRoom;
  axis: 0 | 1;
  onChange: (partial: Partial<DungeonRoom>) => void;
}) => {
  const key = GRID_KEYS[axis];
  const otherKey = GRID_KEYS[1 - axis];
  const defaults = FOOTPRINT[boardTypeOf(room)];
  return (
    <input
      type="number"
      min={GRID_MIN}
      max={GRID_MAX}
      className="input-underline !text-sm !w-16"
      placeholder={String(defaults[axis])}
      title={axis === 0 ? 'Ширина' : 'Глубина'}
      value={room[key] ?? ''}
      onChange={(e) => {
        const raw = e.target.value;
        const value =
          raw === ''
            ? null
            : Math.min(GRID_MAX, Math.max(GRID_MIN, Math.round(Number(raw))));
        // Both sides or neither: a half-set size would fall back to the default anyway.
        onChange({
          [key]: value,
          [otherKey]:
            value === null ? null : (room[otherKey] ?? defaults[1 - axis]),
        });
      }}
    />
  );
};

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

/** Pick a key kind, or none. */
const KeySelect = ({
  value,
  onChange,
  empty = '— Нет —',
}: {
  value: string | null | undefined;
  onChange: (kind: string | null) => void;
  empty?: string;
}) => (
  <select
    className="input-underline !text-sm"
    value={value ?? ''}
    onChange={(e) => onChange(e.target.value || null)}
  >
    <option value="" className="bg-site-dark text-white">
      {empty}
    </option>
    {DUNGEON_KEY_KINDS.map((k) => (
      <option key={k} value={k} className="bg-site-dark text-white">
        {DUNGEON_KEYS[k].name}
      </option>
    ))}
  </select>
);

/** A room that hands the party a key (chest opened / battle won). */
const KeyRewardField = ({
  config,
  onChange,
  label,
}: {
  config: Record<string, unknown>;
  onChange: (c: Record<string, unknown>) => void;
  label: string;
}) => (
  <div className="flex flex-col gap-1">
    <FieldLabel>{label}</FieldLabel>
    <KeySelect
      value={config.key_reward as string | undefined}
      onChange={(kind) => {
        const { key_reward: _old, ...rest } = config;
        onChange(kind ? { ...rest, key_reward: kind } : rest);
      }}
    />
  </div>
);

const OUTCOME_TYPES = [
  { value: 'nothing', label: 'Ничего' },
  { value: 'damage', label: 'Урон' },
  { value: 'reward', label: 'Награда' },
  { value: 'heal', label: 'Лечение' },
  { value: 'teleport', label: 'Телепорт' },
  { value: 'battle', label: 'Бой' },
  { value: 'key', label: 'Ключ' },
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
  /** Every corridor, the passages between floors included. */
  corridors: DungeonCorridor[];
  floorsCount: number;
  onAddCorridor: (corridor: Omit<DungeonCorridor, 'id'>) => void;
  onRoomChange: (room: DungeonRoom) => void;
  onCorridorChange: (corridor: DungeonCorridor) => void;
  onDeleteRoom: (roomId: number) => void;
  onDeleteCorridor: (corridorId: number) => void;
}

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
    <FieldLabel>Мобы</FieldLabel>
    <EntityListPicker
      kind="mob"
      repeats
      ids={(config.mob_template_ids as number[]) ?? []}
      onChange={(mob_template_ids) => onChange({ ...config, mob_template_ids })}
    />
    <KeyRewardField
      config={config}
      onChange={onChange}
      label="Ключ за победу"
    />
  </div>
);

export const LootTable = ({
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
        <div className="flex flex-col gap-0.5 basis-full min-w-0">
          <span className="text-[9px] text-white/40">Предмет</span>
          <EntityPicker
            kind="item"
            value={row.item_id || null}
            onChange={(id) => {
              const updated = [...items];
              updated[idx] = { ...row, item_id: id ?? 0 };
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
      <FieldLabel>Босс и его свита</FieldLabel>
      <EntityListPicker
        kind="mob"
        repeats
        ids={(config.mob_template_ids as number[]) ?? []}
        onChange={(mob_template_ids) => onChange({ ...config, mob_template_ids })}
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
  <div className="flex flex-col gap-3">
    <LootTable
      items={(config.loot_table as LootEntry[]) || []}
      label="Таблица лута"
      onChange={(loot_table) => onChange({ ...config, loot_table })}
    />
    <KeyRewardField
      config={config}
      onChange={onChange}
      label="Ключ в сундуке"
    />
  </div>
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
  const { forms } = useCurrency();
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

  if (outcomeType === 'key') {
    return (
      <div className="flex flex-col gap-0.5">
        <span className="text-[9px] text-white/40">Ключ</span>
        <KeySelect
          value={data.key as string | undefined}
          onChange={(kind) => set('key', kind)}
          empty="— Выберите ключ —"
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
        <span className="text-[9px] text-white/40">Мобы</span>
        <EntityListPicker
          kind="mob"
          repeats
          ids={(data.mob_template_ids as number[]) ?? []}
          onChange={(ids) => set('mob_template_ids', ids)}
        />
      </div>
    );
  }

  if (outcomeType === 'reward') {
    return (
      <div className="flex flex-col gap-1 col-span-2">
        <div className="flex flex-wrap gap-2">
          <div className="flex flex-col gap-0.5 flex-1">
            <span className="text-[9px] text-white/40">{forms.name}</span>
            <input
              type="number"
              className="input-underline !text-sm"
              placeholder="100"
              value={(data.gold as number) ?? ''}
              onChange={(e) => set('gold', Number(e.target.value) || 0)}
            />
          </div>
          <div className="flex flex-col gap-0.5 basis-full order-last min-w-0">
            <span className="text-[9px] text-white/40">Предмет</span>
            <EntityPicker
              kind="item"
              value={((data.items as {item_id: number}[])?.[0]?.item_id) || null}
              onChange={(itemId) => {
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
      <FieldLabel>Стоимость ({getCurrencyForms().name.toLowerCase()})</FieldLabel>
      <input
        type="number"
        className="input-underline !text-sm"
        value={(config.gold_cost as number) ?? 0}
        min={0}
        onChange={(e) => onChange({ ...config, gold_cost: Number(e.target.value) })}
      />
    </div>
    <div className="flex flex-col gap-1">
      <FieldLabel>Шанс ночной вылазки</FieldLabel>
      <input
        type="number"
        className="input-underline !text-sm"
        value={(config.ambush_chance as number) ?? 0}
        min={0}
        max={1}
        step={0.05}
        onChange={(e) =>
          onChange({ ...config, ambush_chance: Math.min(1, Math.max(0, Number(e.target.value) || 0)) })
        }
      />
    </div>
    <div className="flex flex-col gap-1">
      <FieldLabel>Мобы вылазки</FieldLabel>
      <EntityListPicker
        kind="mob"
        repeats
        ids={(config.ambush_mob_ids as number[]) ?? []}
        onChange={(ambush_mob_ids) => onChange({ ...config, ambush_mob_ids })}
      />
    </div>
    <p className="col-span-2 text-white/40 text-[10px]">
      Во время отдыха на привал могут напасть. Дозорный, если не задремлет, поднимет тревогу; иначе начнётся бой, а
      отдых сорвётся. Шанс 0 — привал безопасен.
    </p>
  </div>
);

/** Any room (FEAT-176): darkness, and a stash to be found by searching. */
const DarkAndStashFields = ({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (c: Record<string, unknown>) => void;
}) => {
  const stash = (config.stash ?? null) as { items?: LootEntry[]; difficulty?: number } | null;
  const setStash = (next: { items?: LootEntry[]; difficulty?: number } | null) => {
    const { stash: _old, ...rest } = config;
    void _old;
    onChange(next && (next.items?.length || next.difficulty !== undefined) ? { ...rest, stash: next } : rest);
  };
  return (
    <div className="flex flex-col gap-3">
      <label className="flex items-center gap-2 text-sm text-white/80 cursor-pointer">
        <input
          type="checkbox"
          checked={config.dark === true}
          onChange={(e) => {
            const { dark: _old, ...rest } = config;
            void _old;
            onChange(e.target.checked ? { ...rest, dark: true } : rest);
          }}
        />
        Тёмная комната
      </label>
      <p className="text-white/40 text-[10px] -mt-2">
        Пока не зажгут свет, выходы скрыты, ловушки бьют на 50% больнее, а обыск невозможен.
      </p>
      <LootTable
        items={stash?.items ?? []}
        label="Тайник (найдут при обыске)"
        onChange={(items) => setStash({ ...(stash ?? {}), items })}
      />
      {stash?.items?.length ? (
        <div className="flex flex-col gap-1">
          <FieldLabel>Сложность обыска</FieldLabel>
          <input
            type="number"
            min={0}
            className="input-underline !text-sm !w-24"
            value={stash.difficulty ?? 12}
            onChange={(e) => setStash({ ...stash, difficulty: Math.max(0, Number(e.target.value) || 0) })}
          />
        </div>
      ) : null}
    </div>
  );
};

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
          <div className="flex flex-col gap-0.5 basis-full min-w-0">
            <span className="text-[9px] text-white/40">Предмет</span>
            <EntityPicker
              kind="item"
              value={item.item_id || null}
              onChange={(id) => {
                const updated = [...items];
                updated[idx] = { ...item, item_id: id ?? 0 };
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
}) => {
  const red = config.portal === 'red';
  const others = rooms.filter((r) => r.id !== currentRoomId);
  const redTargets = Array.isArray(config.target_room_ids)
    ? (config.target_room_ids as number[])
    : [];
  const toggleTarget = (id: number) =>
    onChange({
      ...config,
      target_room_ids: redTargets.includes(id)
        ? redTargets.filter((t) => t !== id)
        : [...redTargets, id],
    });
  return (
    <div className="flex flex-col gap-2">
      <FieldLabel>Портал</FieldLabel>
      <div className="flex flex-wrap gap-2">
        {(
          [
            ['blue', 'Синий — по желанию'],
            ['red', 'Красный — ловушка'],
          ] as const
        ).map(([kind, label]) => (
          <button
            key={kind}
            type="button"
            onClick={() => onChange({ ...config, portal: kind })}
            className={`text-xs px-3 py-1.5 rounded-card border transition-colors ${
              (config.portal ?? 'blue') === kind
                ? kind === 'red'
                  ? 'border-red-500/60 bg-red-600/20 text-red-200'
                  : 'border-cyan-500/60 bg-cyan-600/20 text-cyan-100'
                : 'border-white/15 text-white/50 hover:text-white/80'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {red ? (
        <>
          <p className="text-white/40 text-xs">
            При входе группа делает проверку. Успех — портал раскрыт и больше не
            опасен. Провал — группу выбрасывает в случайную комнату из
            отмеченных.
          </p>
          <FieldLabel>Проверяемая характеристика</FieldLabel>
          <select
            className="input-underline !text-sm"
            value={(config.stat_check as string) || 'intelligence'}
            onChange={(e) =>
              onChange({ ...config, stat_check: e.target.value })
            }
          >
            {STAT_CHECK_OPTIONS.map((s) => (
              <option
                key={s.value}
                value={s.value}
                className="bg-site-dark text-white"
              >
                {s.label}
              </option>
            ))}
          </select>
          <FieldLabel>Сложность</FieldLabel>
          <input
            type="number"
            min={0}
            className="input-underline !text-sm"
            value={(config.difficulty as number) ?? 10}
            onChange={(e) =>
              onChange({
                ...config,
                difficulty: Math.max(0, Number(e.target.value) || 0),
              })
            }
          />
          <FieldLabel>Куда может выбросить</FieldLabel>
          <div className="flex flex-col gap-1 max-h-48 overflow-y-auto pr-1">
            {others.map((r) => (
              <label
                key={r.id}
                className="flex items-center gap-2 text-sm text-white/80 cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={redTargets.includes(r.id)}
                  onChange={() => toggleTarget(r.id)}
                />
                <span className="break-words">
                  {r.name} ({ROOM_TYPE_LABELS[r.room_type] || r.room_type})
                </span>
              </label>
            ))}
          </div>
        </>
      ) : (
        <>
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
            {others.map((r) => (
              <option
                key={r.id}
                value={r.id}
                className="bg-site-dark text-white"
              >
                {r.name} ({ROOM_TYPE_LABELS[r.room_type] || r.room_type})
              </option>
            ))}
          </select>
        </>
      )}
    </div>
  );
};

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
  corridors,
  floorsCount,
  onAddCorridor,
  onCorridorChange,
  onDeleteCorridor,
  onRoomChange,
  onDeleteRoom,
}: {
  room: DungeonRoom;
  rooms: DungeonRoom[];
  corridors: DungeonCorridor[];
  floorsCount: number;
  onAddCorridor: (corridor: Omit<DungeonCorridor, 'id'>) => void;
  onCorridorChange: (corridor: DungeonCorridor) => void;
  onDeleteCorridor: (corridorId: number) => void;
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

      {/* Footprint on the 3D miniature; empty = the usual size for the room's kind */}
      <div className="flex flex-col gap-1">
        <FieldLabel>Размер на макете (клетки)</FieldLabel>
        <div className="flex items-center gap-2">
          <SizeInput room={room} axis={0} onChange={update} />
          <span className="text-white/40 text-xs">×</span>
          <SizeInput room={room} axis={1} onChange={update} />
        </div>
        <p className="text-[10px] text-white/40">
          Пусто — обычный размер для типа комнаты.
        </p>
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

      <SectionHeader>Этаж</SectionHeader>
      <select
        className="input-underline !text-sm !w-32"
        value={room.floor ?? 1}
        onChange={(e) => update({ floor: Number(e.target.value) })}
      >
        {Array.from({ length: floorsCount + 1 }, (_, i) => i + 1).map((f) => (
          <option key={f} value={f} className="bg-site-dark text-white">
            Этаж {f}
          </option>
        ))}
      </select>

      <SectionHeader>Переходы между этажами</SectionHeader>
      <PassagesEditor
        room={room}
        rooms={rooms}
        corridors={corridors}
        onAdd={onAddCorridor}
        onChange={onCorridorChange}
        onDelete={onDeleteCorridor}
      />

      <SectionHeader>Рычаг</SectionHeader>
      <LeverField
        config={room.room_config || {}}
        rooms={rooms}
        corridors={corridors}
        onChange={(room_config) => update({ room_config })}
      />

      <SectionHeader>Темнота и тайник</SectionHeader>
      <DarkAndStashFields
        config={room.room_config || {}}
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

// --- Passages between floors ---

const PASSAGE_OPTIONS = [
  { value: 'stairs', label: 'Лестница' },
  { value: 'drop', label: 'Провал (только вниз)' },
  { value: 'lift', label: 'Подъёмник' },
] as const;

const PassagesEditor = ({
  room,
  rooms,
  corridors,
  onAdd,
  onChange,
  onDelete,
}: {
  room: DungeonRoom;
  rooms: DungeonRoom[];
  corridors: DungeonCorridor[];
  onAdd: (corridor: Omit<DungeonCorridor, 'id'>) => void;
  onChange: (corridor: DungeonCorridor) => void;
  onDelete: (corridorId: number) => void;
}) => {
  const floor = room.floor ?? 1;
  const [kind, setKind] = useState<'stairs' | 'drop' | 'lift'>('stairs');
  const [target, setTarget] = useState<number | ''>('');
  const nameOf = (id: number) =>
    rooms.find((r) => r.id === id)?.name ?? `#${id}`;
  const floorOfId = (id: number) => rooms.find((r) => r.id === id)?.floor ?? 1;
  const mine = corridors.filter(
    (c) =>
      (c.passage_type ?? 'corridor') !== 'corridor' &&
      (c.from_room_id === room.id || c.to_room_id === room.id),
  );
  // A drop only goes down; stairs and lifts go one floor either way.
  const targets = rooms.filter((r) => {
    const f = r.floor ?? 1;
    return kind === 'drop' ? f === floor + 1 : Math.abs(f - floor) === 1;
  });

  return (
    <div className="flex flex-col gap-2">
      {mine.length === 0 && (
        <p className="text-white/40 text-xs">
          Отсюда нет переходов на другие этажи.
        </p>
      )}
      {mine.map((c) => {
        const other =
          c.from_room_id === room.id ? c.to_room_id : c.from_room_id;
        const cfg = (c.passage_config ?? {}) as Record<string, unknown>;
        const hidden = !!cfg.hidden;
        const setCfg = (partial: Record<string, unknown>) =>
          onChange({ ...c, passage_config: { ...cfg, ...partial } });
        return (
          <div
            key={c.id}
            className="flex flex-col gap-1.5 rounded border border-white/10 p-2"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-white/80 break-words">
                {c.passage_type === 'drop' && c.to_room_id === room.id
                  ? `Сюда падают из «${nameOf(other)}» (этаж ${floorOfId(other)})`
                  : `${PASSAGE_OPTIONS.find((o) => o.value === c.passage_type)?.label} → ${nameOf(other)} (этаж ${floorOfId(other)})`}
              </span>
              <button
                type="button"
                onClick={() => onDelete(c.id)}
                className="text-site-red/80 hover:text-site-red text-xs shrink-0"
              >
                Удалить
              </button>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-white/40">Стамина</span>
              <input
                type="number"
                min={0}
                className="input-underline !text-sm !w-16"
                value={c.stamina_cost}
                onChange={(e) =>
                  onChange({
                    ...c,
                    stamina_cost: Math.max(0, Number(e.target.value) || 0),
                  })
                }
              />
            </div>
            {c.passage_type === 'drop' && (
              <>
                <label className="flex items-center gap-2 text-xs text-white cursor-pointer">
                  <input
                    type="checkbox"
                    checked={hidden}
                    onChange={(e) => setCfg({ hidden: e.target.checked })}
                    className="accent-gold w-3.5 h-3.5"
                  />
                  Скрытый: ловушка при входе в комнату
                </label>
                {hidden && (
                  <div className="grid grid-cols-3 gap-2">
                    <select
                      className="input-underline !text-xs"
                      value={(cfg.stat_check as string) || 'intelligence'}
                      onChange={(e) => setCfg({ stat_check: e.target.value })}
                    >
                      {STAT_CHECK_OPTIONS.map((s) => (
                        <option
                          key={s.value}
                          value={s.value}
                          className="bg-site-dark text-white"
                        >
                          {s.label}
                        </option>
                      ))}
                    </select>
                    <input
                      type="number"
                      min={0}
                      title="Сложность"
                      className="input-underline !text-xs"
                      value={(cfg.difficulty as number) ?? 12}
                      onChange={(e) =>
                        setCfg({
                          difficulty: Math.max(0, Number(e.target.value) || 0),
                        })
                      }
                    />
                    <input
                      type="number"
                      min={0}
                      title="Урон при падении"
                      className="input-underline !text-xs"
                      value={(cfg.fail_damage as number) ?? 15}
                      onChange={(e) =>
                        setCfg({
                          fail_damage: Math.max(0, Number(e.target.value) || 0),
                        })
                      }
                    />
                  </div>
                )}
              </>
            )}
            {c.passage_type === 'lift' && (
              <>
                <KeySelect
                  value={c.lock_config?.key}
                  empty={
                    c.lock_config?.lever ? '— Без ключа —' : '— Не заперт —'
                  }
                  onChange={(k) =>
                    onChange({
                      ...c,
                      lock_config: k
                        ? { pickable: false, ...c.lock_config, key: k }
                        : c.lock_config?.lever
                          ? { ...c.lock_config, key: null }
                          : null,
                    })
                  }
                />
                <label className="flex items-center gap-2 text-xs text-white cursor-pointer">
                  <input
                    type="checkbox"
                    checked={!!c.lock_config?.lever}
                    onChange={(e) =>
                      onChange({
                        ...c,
                        lock_config: e.target.checked
                          ? { pickable: false, ...c.lock_config, lever: true }
                          : c.lock_config?.key
                            ? { ...c.lock_config, lever: false }
                            : null,
                      })
                    }
                    className="accent-gold w-3.5 h-3.5"
                  />
                  Включается рычагом
                </label>
              </>
            )}
          </div>
        );
      })}

      <div className="flex flex-col gap-1.5 rounded border border-dashed border-white/15 p-2">
        <span className="text-[10px] text-white/40">Новый переход</span>
        <select
          className="input-underline !text-sm"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value as typeof kind);
            setTarget('');
          }}
        >
          {PASSAGE_OPTIONS.map((o) => (
            <option
              key={o.value}
              value={o.value}
              className="bg-site-dark text-white"
            >
              {o.label}
            </option>
          ))}
        </select>
        <select
          className="input-underline !text-sm"
          value={target}
          onChange={(e) =>
            setTarget(e.target.value ? Number(e.target.value) : '')
          }
        >
          <option value="" className="bg-site-dark text-white">
            {targets.length ? '— Куда —' : 'На соседнем этаже нет комнат'}
          </option>
          {targets.map((r) => (
            <option key={r.id} value={r.id} className="bg-site-dark text-white">
              {r.name} (этаж {r.floor ?? 1})
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={target === ''}
          onClick={() => {
            if (target === '') return;
            onAdd({
              dungeon_id: room.dungeon_id,
              from_room_id: room.id,
              to_room_id: target,
              stamina_cost: 1,
              is_bidirectional: kind !== 'drop',
              random_battle_chance: 0,
              random_battle_mob_ids: null,
              trap_chance: 0,
              trap_config: null,
              lock_config: null,
              passage_type: kind,
              passage_config: null,
              description: null,
              source_handle: null,
              target_handle: null,
            });
            setTarget('');
          }}
          className="text-xs px-3 py-1.5 rounded border border-white/20 text-white/80 hover:text-white disabled:opacity-40"
        >
          Добавить переход
        </button>
      </div>
    </div>
  );
};

/** A lever in this room: which locked door or lift it opens. */
const LeverField = ({
  config,
  rooms,
  corridors,
  onChange,
}: {
  config: Record<string, unknown>;
  rooms: DungeonRoom[];
  corridors: DungeonCorridor[];
  onChange: (c: Record<string, unknown>) => void;
}) => {
  const nameOf = (id: number) =>
    rooms.find((r) => r.id === id)?.name ?? `#${id}`;
  // Only saved corridors: the server checks the lever's target exists.
  const lockable = corridors.filter((c) => c.id > 0 && c.lock_config?.lever);
  const value = (config.lever_corridor_id as number | undefined) ?? '';
  return (
    <div className="flex flex-col gap-1">
      <select
        className="input-underline !text-sm"
        value={value}
        onChange={(e) => {
          const { lever_corridor_id: _old, ...rest } = config;
          onChange(
            e.target.value
              ? { ...rest, lever_corridor_id: Number(e.target.value) }
              : rest,
          );
        }}
      >
        <option value="" className="bg-site-dark text-white">
          — Нет рычага —
        </option>
        {lockable.map((c) => (
          <option key={c.id} value={c.id} className="bg-site-dark text-white">
            {nameOf(c.from_room_id)} — {nameOf(c.to_room_id)}
          </option>
        ))}
      </select>
      <p className="text-white/40 text-[10px]">
        Список — сохранённые двери и подъёмники с галочкой «рычагом». Новый
        коридор сначала сохраните.
      </p>
    </div>
  );
};

// --- Corridor Panel ---

/** Secret ways out (FEAT-176): each opened by one class's craft, by anyone at a cost. */
const SECRET_OPTIONS = [
  { value: 'mechanism', label: 'Скрытый механизм (плут, ловкость)' },
  { value: 'illusion', label: 'Иллюзорная стена (маг, интеллект)' },
  { value: 'rubble', label: 'Завал (воин, сила)' },
];
const SECRET_HINT_PLACEHOLDERS: Record<string, string> = {
  mechanism: 'Плиты пола у одной из стен стёрты сильнее, чем везде…',
  illusion: 'Одна из стен будто чуть дрожит…',
  rubble: 'У стены громоздится завал, из-за камней тянет сквозняком…',
};
const SECRET_HINT_MAX = 300;
/** A gate down across the corridor (FEAT-176): held up and propped by someone strong. */
const GATE_OPTIONS = [
  { value: 'grate', label: 'Решётка' },
  { value: 'slab', label: 'Каменная плита' },
];

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
  const lock = corridor.lock_config ?? null;
  const setLock = (
    partial: Partial<NonNullable<DungeonCorridor['lock_config']>>,
  ) => update({ lock_config: lock ? { ...lock, ...partial } : null });
  const passageConfig = (corridor.passage_config ?? {}) as Record<
    string,
    unknown
  >;
  const secret = (passageConfig.secret ?? null) as Record<
    string,
    unknown
  > | null;
  const setSecret = (next: Record<string, unknown> | null) => {
    const { secret: _old, ...rest } = passageConfig;
    void _old;
    const config = next ? { ...rest, secret: next } : rest;
    update({ passage_config: Object.keys(config).length ? config : null });
  };
  const gate = (passageConfig.gate ?? null) as Record<string, unknown> | null;
  const seal = (passageConfig.seal ?? null) as Record<string, unknown> | null;
  const setSeal = (next: Record<string, unknown> | null) => {
    const { seal: _old, ...rest } = passageConfig;
    void _old;
    const config = next ? { ...rest, seal: next } : rest;
    update({ passage_config: Object.keys(config).length ? config : null });
  };
  const setGate = (next: Record<string, unknown> | null) => {
    const { gate: _old, ...rest } = passageConfig;
    void _old;
    const config = next ? { ...rest, gate: next } : rest;
    update({ passage_config: Object.keys(config).length ? config : null });
  };

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
          <FieldLabel>Мобы</FieldLabel>
          <EntityListPicker
            kind="mob"
            repeats
            ids={corridor.random_battle_mob_ids ?? []}
            onChange={(ids) => update({ random_battle_mob_ids: ids.length > 0 ? ids : null })}
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

      {!gate && (
        <>
          {/* Secret way */}
          <SectionHeader>Тайный проход</SectionHeader>

          <div className="flex flex-col gap-1">
            <FieldLabel>Вид</FieldLabel>
            <select
              className="input-underline !text-sm"
              value={(secret?.kind as string) ?? ''}
              onChange={(e) =>
                setSecret(
                  e.target.value ? { ...secret, kind: e.target.value } : null,
                )
              }
            >
              <option value="" className="bg-site-dark text-white">
                — Обычный коридор —
              </option>
              {SECRET_OPTIONS.map((o) => (
                <option
                  key={o.value}
                  value={o.value}
                  className="bg-site-dark text-white"
                >
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          {secret && (
            <div className="flex flex-col gap-2">
              <div className="grid grid-cols-2 gap-2">
                <div className="flex flex-col gap-1">
                  <FieldLabel>Сложность</FieldLabel>
                  <input
                    type="number"
                    min={0}
                    className="input-underline !text-sm"
                    value={(secret.difficulty as number) ?? 12}
                    onChange={(e) =>
                      setSecret({
                        ...secret,
                        difficulty: Math.max(0, Number(e.target.value) || 0),
                      })
                    }
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <FieldLabel>Стамина за попытку</FieldLabel>
                  <input
                    type="number"
                    min={0}
                    className="input-underline !text-sm"
                    value={(secret.cost as number) ?? 2}
                    onChange={(e) =>
                      setSecret({
                        ...secret,
                        cost: Math.max(0, Number(e.target.value) || 0),
                      })
                    }
                  />
                </div>
              </div>
              {secret.kind === 'rubble' && (
                <div className="flex flex-col gap-1">
                  <FieldLabel>Урон при обвале</FieldLabel>
                  <input
                    type="number"
                    min={0}
                    className="input-underline !text-sm !w-24"
                    value={(secret.fail_damage as number) ?? 10}
                    onChange={(e) =>
                      setSecret({
                        ...secret,
                        fail_damage: Math.max(0, Number(e.target.value) || 0),
                      })
                    }
                  />
                </div>
              )}
              <div className="flex flex-col gap-1">
                <FieldLabel>Подсказка игрокам (пусто — стандартная)</FieldLabel>
                <textarea
                  className="input-underline !text-sm resize-none"
                  rows={2}
                  maxLength={SECRET_HINT_MAX}
                  placeholder={SECRET_HINT_PLACEHOLDERS[secret.kind as string]}
                  value={(secret.hint as string) ?? ''}
                  onChange={(e) =>
                    setSecret({ ...secret, hint: e.target.value || undefined })
                  }
                />
              </div>
              <p className="text-white/40 text-[10px]">
                Проход не виден, пока его не откроют из комнаты «
                {fromRoom?.name || `#${corridor.from_room_id}`}»: там игроки
                видят подсказку. Открыть может любой, но своему классу легче.
              </p>
            </div>
          )}
        </>
      )}

      {/* Gate */}
      {!secret && (
        <>
          <SectionHeader>Решётка</SectionHeader>
          <div className="flex flex-col gap-1">
            <FieldLabel>Перекрыт</FieldLabel>
            <select
              className="input-underline !text-sm"
              value={(gate?.look as string) ?? ''}
              onChange={(e) =>
                setGate(
                  e.target.value ? { ...gate, look: e.target.value } : null,
                )
              }
            >
              <option value="" className="bg-site-dark text-white">
                — Нет —
              </option>
              {GATE_OPTIONS.map((o) => (
                <option
                  key={o.value}
                  value={o.value}
                  className="bg-site-dark text-white"
                >
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          {gate && (
            <div className="flex flex-col gap-2">
              <div className="grid grid-cols-3 gap-2">
                <div className="flex flex-col gap-1">
                  <FieldLabel>Сложность</FieldLabel>
                  <input
                    type="number"
                    min={0}
                    className="input-underline !text-sm"
                    value={(gate.difficulty as number) ?? 12}
                    onChange={(e) =>
                      setGate({
                        ...gate,
                        difficulty: Math.max(0, Number(e.target.value) || 0),
                      })
                    }
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <FieldLabel>Стамина</FieldLabel>
                  <input
                    type="number"
                    min={0}
                    className="input-underline !text-sm"
                    value={(gate.cost as number) ?? 2}
                    onChange={(e) =>
                      setGate({
                        ...gate,
                        cost: Math.max(0, Number(e.target.value) || 0),
                      })
                    }
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <FieldLabel>Урон</FieldLabel>
                  <input
                    type="number"
                    min={0}
                    className="input-underline !text-sm"
                    value={(gate.fail_damage as number) ?? 10}
                    onChange={(e) =>
                      setGate({
                        ...gate,
                        fail_damage: Math.max(0, Number(e.target.value) || 0),
                      })
                    }
                  />
                </div>
              </div>
              <p className="text-white/40 text-[10px]">
                Пройти нельзя, пока кто-то не поднимет и не подопрёт её (с обеих
                сторон коридора); дальше проход открыт до конца забега. Сорвётся
                — урон тому, кто держал. Лучше не совмещать с замком: открытие
                одного откроет и другое.
              </p>
            </div>
          )}
        </>
      )}

      {/* Seal */}
      {!secret && !gate && (
        <>
          <SectionHeader>Магическая печать</SectionHeader>
          <label className="flex items-center gap-2 text-sm text-white/80 cursor-pointer">
            <input type="checkbox" checked={!!seal} onChange={(e) => setSeal(e.target.checked ? {} : null)} />
            Проход запечатан
          </label>
          {seal && (
            <div className="flex flex-col gap-2">
              <div className="grid grid-cols-3 gap-2">
                {(
                  [
                    ['difficulty', 'Сложность', 12],
                    ['cost', 'Стамина', 2],
                    ['fail_damage', 'Урон', 12],
                  ] as const
                ).map(([field, label, fallback]) => (
                  <div key={field} className="flex flex-col gap-1">
                    <FieldLabel>{label}</FieldLabel>
                    <input
                      type="number"
                      min={0}
                      className="input-underline !text-sm"
                      value={(seal[field] as number) ?? fallback}
                      onChange={(e) => setSeal({ ...seal, [field]: Math.max(0, Number(e.target.value) || 0) })}
                    />
                  </div>
                ))}
              </div>
              <p className="text-white/40 text-[10px]">
                Пройти нельзя (с обеих сторон), пока печать не снимут — это ремесло мага, мини-игра или бросок
                интеллекта. Сорвётся — урон тому, кто снимал. Не совмещайте с замком.
              </p>
            </div>
          )}
        </>
      )}

      {/* Lock */}
      <SectionHeader>Замок</SectionHeader>

      <div className="flex flex-col gap-1">
        <FieldLabel>Дверь открывает</FieldLabel>
        <KeySelect
          value={lock?.key}
          empty={lock?.lever ? '— Без ключа —' : '— Не заперта —'}
          onChange={(kind) =>
            update({
              lock_config: kind
                ? { pickable: true, ...lock, key: kind }
                : lock?.lever
                  ? { ...lock, key: null }
                  : null,
            })
          }
        />
      </div>

      <label className="flex items-center gap-2 text-xs text-white cursor-pointer">
        <input
          type="checkbox"
          checked={!!lock?.lever}
          onChange={(e) =>
            update({
              lock_config: e.target.checked
                ? { pickable: false, ...lock, lever: true }
                : lock?.key
                  ? { ...lock, lever: false }
                  : null,
            })
          }
          className="accent-gold w-3.5 h-3.5"
        />
        Открывается рычагом (рычаг ставится в комнате)
      </label>

      {lock && (
        <div className="flex flex-col gap-2">
          <label className="flex items-center gap-2 text-xs text-white cursor-pointer">
            <input
              type="checkbox"
              checked={lock.pickable !== false}
              onChange={(e) => setLock({ pickable: e.target.checked })}
              className="accent-gold w-3.5 h-3.5"
            />
            Можно взломать без ключа
          </label>
          {lock.pickable !== false && (
            <>
              <div className="flex flex-col gap-1">
                <FieldLabel>Характеристика взлома</FieldLabel>
                <select
                  className="input-underline !text-sm"
                  value={lock.stat_check || 'agility'}
                  onChange={(e) => setLock({ stat_check: e.target.value })}
                >
                  {STAT_CHECK_OPTIONS.map((s) => (
                    <option
                      key={s.value}
                      value={s.value}
                      className="bg-site-dark text-white"
                    >
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
                    min={0}
                    className="input-underline !text-sm"
                    value={lock.difficulty ?? 12}
                    onChange={(e) =>
                      setLock({
                        difficulty: Math.max(0, Number(e.target.value) || 0),
                      })
                    }
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <FieldLabel>Стамина за попытку</FieldLabel>
                  <input
                    type="number"
                    min={0}
                    className="input-underline !text-sm"
                    value={lock.pick_cost ?? 2}
                    onChange={(e) =>
                      setLock({
                        pick_cost: Math.max(0, Number(e.target.value) || 0),
                      })
                    }
                  />
                </div>
              </div>
            </>
          )}
          <p className="text-white/40 text-[10px]">
            Ключ выдаётся в сундуке сокровищницы, за победу в боевой комнате или
            исходом события и открывает все двери своего цвета до конца забега.
          </p>
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
  corridors,
  floorsCount,
  onAddCorridor,
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
          corridors={corridors}
          floorsCount={floorsCount}
          onAddCorridor={onAddCorridor}
          onCorridorChange={onCorridorChange}
          onDeleteCorridor={onDeleteCorridor}
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
