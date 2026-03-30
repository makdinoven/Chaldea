import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import toast from 'react-hot-toast';
import type { DungeonRoom } from '../../../api/dungeons';

// --- Types for room_config by room_type ---

interface LootEntry {
  item_id: number;
  quantity: number;
  chance: number;
}

interface EventChoice {
  text: string;
  outcome_type: 'reward' | 'damage' | 'teleport' | 'nothing';
  outcome_data: string; // JSON string for flexibility
}

interface MerchantItem {
  item_id: number;
  price: number;
  stock: number;
}

// --- Constants ---

const ROOM_TYPES = [
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
] as const;

type RoomType = (typeof ROOM_TYPES)[number]['value'];

const STAT_CHECK_OPTIONS = [
  { value: 'strength', label: 'Сила' },
  { value: 'agility', label: 'Ловкость' },
  { value: 'intelligence', label: 'Интеллект' },
  { value: 'endurance', label: 'Выносливость' },
  { value: 'charisma', label: 'Харизма' },
  { value: 'luck', label: 'Удача' },
];

const OUTCOME_TYPES = [
  { value: 'reward', label: 'Награда' },
  { value: 'damage', label: 'Урон' },
  { value: 'teleport', label: 'Телепорт' },
  { value: 'nothing', label: 'Ничего' },
];

interface FormState {
  room_type: RoomType;
  name: string;
  description: string;
  image_url: string;
  sort_order: number;
  is_entrance: boolean;
  is_boss_room: boolean;
  is_mana_core_room: boolean;
  // Config fields by type
  mob_template_ids: string;
  boss_loot: LootEntry[];
  loot_table: LootEntry[];
  stat_check: string;
  difficulty: number;
  fail_damage: number;
  fail_effect: string;
  event_text: string;
  event_choices: EventChoice[];
  heal_percent: number;
  wait_seconds: number;
  gold_cost: number;
  merchant_items: MerchantItem[];
  target_room_id: number | null;
}

const INITIAL_FORM: FormState = {
  room_type: 'fork',
  name: '',
  description: '',
  image_url: '',
  sort_order: 0,
  is_entrance: false,
  is_boss_room: false,
  is_mana_core_room: false,
  mob_template_ids: '',
  boss_loot: [],
  loot_table: [],
  stat_check: 'agility',
  difficulty: 10,
  fail_damage: 20,
  fail_effect: '',
  event_text: '',
  event_choices: [],
  heal_percent: 30,
  wait_seconds: 300,
  gold_cost: 0,
  merchant_items: [],
  target_room_id: null,
};

const AdminDungeonRoomForm = () => {
  const { id, roomId } = useParams<{ id: string; roomId?: string }>();
  const navigate = useNavigate();
  const dungeonId = Number(id);
  const isEdit = !!roomId;

  const [form, setForm] = useState<FormState>({ ...INITIAL_FORM });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rooms, setRooms] = useState<DungeonRoom[]>([]);

  // Load existing room data if editing
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      try {
        // Load dungeon to get rooms list (for teleport dropdown)
        const { data: dungeonData } = await axios.get(`/dungeons/admin/dungeons/${dungeonId}`);
        setRooms(dungeonData.rooms || []);

        if (isEdit && roomId) {
          const room = (dungeonData.rooms as DungeonRoom[]).find(
            (r: DungeonRoom) => r.id === Number(roomId)
          );
          if (room) {
            populateForm(room);
          } else {
            toast.error('Комната не найдена');
            navigate(`/admin/dungeons/${dungeonId}`);
          }
        }
      } catch {
        toast.error('Ошибка загрузки данных');
      } finally {
        setLoading(false);
      }
    };
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dungeonId, roomId]);

  const populateForm = (room: DungeonRoom) => {
    const config = (room.room_config || {}) as Record<string, unknown>;
    const newForm: FormState = {
      ...INITIAL_FORM,
      room_type: room.room_type as RoomType,
      name: room.name,
      description: room.description,
      image_url: room.image_url || '',
      sort_order: room.sort_order,
      is_entrance: room.is_entrance,
      is_boss_room: room.is_boss_room,
      is_mana_core_room: room.is_mana_core_room,
    };

    switch (room.room_type) {
      case 'battle':
        newForm.mob_template_ids = ((config.mob_template_ids as number[]) || []).join(', ');
        break;
      case 'boss':
        newForm.mob_template_ids = ((config.mob_template_ids as number[]) || []).join(', ');
        newForm.boss_loot = (config.boss_loot as LootEntry[]) || [];
        break;
      case 'treasure':
        newForm.loot_table = (config.loot_table as LootEntry[]) || [];
        break;
      case 'trap':
        newForm.stat_check = (config.stat_check as string) || 'agility';
        newForm.difficulty = (config.difficulty as number) || 10;
        newForm.fail_damage = (config.fail_damage as number) || 20;
        newForm.fail_effect = (config.fail_effect as string) || '';
        break;
      case 'event':
        newForm.event_text = (config.text as string) || '';
        newForm.event_choices = (config.choices as EventChoice[]) || [];
        break;
      case 'rest':
        newForm.heal_percent = (config.heal_percent as number) || 30;
        newForm.wait_seconds = (config.wait_seconds as number) || 300;
        newForm.gold_cost = (config.gold_cost as number) || 0;
        break;
      case 'merchant':
        newForm.merchant_items = (config.items as MerchantItem[]) || [];
        break;
      case 'teleport':
        newForm.target_room_id = (config.target_room_id as number) || null;
        break;
    }

    setForm(newForm);
  };

  const buildRoomConfig = (): Record<string, unknown> => {
    switch (form.room_type) {
      case 'battle':
        return {
          mob_template_ids: parseMobIds(form.mob_template_ids),
        };
      case 'boss':
        return {
          mob_template_ids: parseMobIds(form.mob_template_ids),
          boss_loot: form.boss_loot,
        };
      case 'treasure':
        return { loot_table: form.loot_table };
      case 'trap':
        return {
          stat_check: form.stat_check,
          difficulty: form.difficulty,
          fail_damage: form.fail_damage,
          fail_effect: form.fail_effect || null,
        };
      case 'event':
        return {
          text: form.event_text,
          choices: form.event_choices.map((c) => ({
            text: c.text,
            outcome_type: c.outcome_type,
            outcome_data: parseJsonSafe(c.outcome_data),
          })),
        };
      case 'rest':
        return {
          heal_percent: form.heal_percent,
          wait_seconds: form.wait_seconds,
          gold_cost: form.gold_cost,
        };
      case 'merchant':
        return { items: form.merchant_items };
      case 'teleport':
        return { target_room_id: form.target_room_id };
      case 'fork':
      case 'deadend':
      default:
        return {};
    }
  };

  const parseMobIds = (str: string): number[] => {
    return str
      .split(/[,\s]+/)
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => !isNaN(n));
  };

  const parseJsonSafe = (str: string): unknown => {
    try {
      return JSON.parse(str || '{}');
    } catch {
      return {};
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) {
      toast.error('Название комнаты обязательно');
      return;
    }
    if (!form.description.trim()) {
      toast.error('Описание комнаты обязательно');
      return;
    }

    setSaving(true);
    const payload = {
      room_type: form.room_type,
      name: form.name.trim(),
      description: form.description.trim(),
      image_url: form.image_url.trim() || null,
      sort_order: form.sort_order,
      is_entrance: form.is_entrance,
      is_boss_room: form.is_boss_room,
      is_mana_core_room: form.is_mana_core_room,
      room_config: buildRoomConfig(),
    };

    try {
      if (isEdit && roomId) {
        await axios.put(`/dungeons/admin/rooms/${roomId}`, payload);
        toast.success('Комната обновлена');
      } else {
        await axios.post(`/dungeons/admin/dungeons/${dungeonId}/rooms`, payload);
        toast.success('Комната создана');
      }
      navigate(`/admin/dungeons/${dungeonId}`);
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? String(err.response.data.detail)
          : 'Не удалось сохранить комнату';
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const updateField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  // --- Loot table helpers ---
  const addLootRow = (field: 'loot_table' | 'boss_loot') => {
    setForm((prev) => ({
      ...prev,
      [field]: [...prev[field], { item_id: 0, quantity: 1, chance: 1.0 }],
    }));
  };

  const updateLootRow = (field: 'loot_table' | 'boss_loot', idx: number, key: keyof LootEntry, value: number) => {
    setForm((prev) => ({
      ...prev,
      [field]: prev[field].map((row, i) => (i === idx ? { ...row, [key]: value } : row)),
    }));
  };

  const removeLootRow = (field: 'loot_table' | 'boss_loot', idx: number) => {
    setForm((prev) => ({
      ...prev,
      [field]: prev[field].filter((_, i) => i !== idx),
    }));
  };

  // --- Event choice helpers ---
  const addChoice = () => {
    setForm((prev) => ({
      ...prev,
      event_choices: [...prev.event_choices, { text: '', outcome_type: 'nothing', outcome_data: '{}' }],
    }));
  };

  const updateChoice = (idx: number, key: keyof EventChoice, value: string) => {
    setForm((prev) => ({
      ...prev,
      event_choices: prev.event_choices.map((c, i) => (i === idx ? { ...c, [key]: value } : c)),
    }));
  };

  const removeChoice = (idx: number) => {
    setForm((prev) => ({
      ...prev,
      event_choices: prev.event_choices.filter((_, i) => i !== idx),
    }));
  };

  // --- Merchant item helpers ---
  const addMerchantItem = () => {
    setForm((prev) => ({
      ...prev,
      merchant_items: [...prev.merchant_items, { item_id: 0, price: 100, stock: 5 }],
    }));
  };

  const updateMerchantItem = (idx: number, key: keyof MerchantItem, value: number) => {
    setForm((prev) => ({
      ...prev,
      merchant_items: prev.merchant_items.map((m, i) => (i === idx ? { ...m, [key]: value } : m)),
    }));
  };

  const removeMerchantItem = (idx: number) => {
    setForm((prev) => ({
      ...prev,
      merchant_items: prev.merchant_items.filter((_, i) => i !== idx),
    }));
  };

  if (loading) {
    return (
      <div className="w-full max-w-[900px] mx-auto flex items-center justify-center py-12">
        <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

  // --- Render loot table ---
  const renderLootTable = (field: 'loot_table' | 'boss_loot', label: string) => (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <label className="text-sm text-white/70">{label}</label>
        <button type="button" onClick={() => addLootRow(field)} className="text-xs text-site-blue hover:text-white transition-colors">
          + Добавить строку
        </button>
      </div>
      {form[field].map((row, idx) => (
        <div key={idx} className="flex flex-wrap gap-2 items-center bg-white/[0.03] rounded-card p-3">
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-white/40">ID предмета</span>
            <input
              type="number"
              className="input-underline !w-24"
              value={row.item_id}
              onChange={(e) => updateLootRow(field, idx, 'item_id', Number(e.target.value))}
            />
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-white/40">Кол-во</span>
            <input
              type="number"
              className="input-underline !w-20"
              value={row.quantity}
              min={1}
              onChange={(e) => updateLootRow(field, idx, 'quantity', Number(e.target.value))}
            />
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-white/40">Шанс (0-1)</span>
            <input
              type="number"
              className="input-underline !w-24"
              value={row.chance}
              step={0.05}
              min={0}
              max={1}
              onChange={(e) => updateLootRow(field, idx, 'chance', Number(e.target.value))}
            />
          </div>
          <button
            type="button"
            onClick={() => removeLootRow(field, idx)}
            className="text-site-red text-xs hover:text-white transition-colors mt-4"
          >
            Удалить
          </button>
        </div>
      ))}
    </div>
  );

  // --- Dynamic config section ---
  const renderConfigFields = () => {
    switch (form.room_type) {
      case 'battle':
        return (
          <div className="flex flex-col gap-3">
            <label className="text-sm text-white/70">ID шаблонов мобов (через запятую)</label>
            <input
              className="input-underline"
              placeholder="1, 2, 3"
              value={form.mob_template_ids}
              onChange={(e) => updateField('mob_template_ids', e.target.value)}
            />
          </div>
        );

      case 'boss':
        return (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-3">
              <label className="text-sm text-white/70">ID шаблонов мобов (через запятую)</label>
              <input
                className="input-underline"
                placeholder="5"
                value={form.mob_template_ids}
                onChange={(e) => updateField('mob_template_ids', e.target.value)}
              />
            </div>
            {renderLootTable('boss_loot', 'Лут босса')}
          </div>
        );

      case 'treasure':
        return renderLootTable('loot_table', 'Таблица лута');

      case 'trap':
        return (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <label className="text-sm text-white/70">Проверяемая характеристика</label>
              <select
                className="input-underline"
                value={form.stat_check}
                onChange={(e) => updateField('stat_check', e.target.value)}
              >
                {STAT_CHECK_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value} className="bg-site-dark text-white">
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="flex flex-col gap-2">
                <label className="text-sm text-white/70">Сложность</label>
                <input
                  type="number"
                  className="input-underline"
                  value={form.difficulty}
                  onChange={(e) => updateField('difficulty', Number(e.target.value))}
                />
              </div>
              <div className="flex flex-col gap-2">
                <label className="text-sm text-white/70">Урон при провале</label>
                <input
                  type="number"
                  className="input-underline"
                  value={form.fail_damage}
                  onChange={(e) => updateField('fail_damage', Number(e.target.value))}
                />
              </div>
              <div className="flex flex-col gap-2">
                <label className="text-sm text-white/70">Эффект при провале</label>
                <input
                  className="input-underline"
                  placeholder="poison, stun, ..."
                  value={form.fail_effect}
                  onChange={(e) => updateField('fail_effect', e.target.value)}
                />
              </div>
            </div>
          </div>
        );

      case 'event':
        return (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <label className="text-sm text-white/70">Текст события</label>
              <textarea
                className="textarea-bordered"
                rows={4}
                placeholder="Описание события..."
                value={form.event_text}
                onChange={(e) => updateField('event_text', e.target.value)}
              />
            </div>
            <div className="flex items-center justify-between">
              <label className="text-sm text-white/70">Варианты выбора</label>
              <button type="button" onClick={addChoice} className="text-xs text-site-blue hover:text-white transition-colors">
                + Добавить вариант
              </button>
            </div>
            {form.event_choices.map((choice, idx) => (
              <div key={idx} className="bg-white/[0.03] rounded-card p-3 flex flex-col gap-3">
                <div className="flex flex-col gap-2">
                  <span className="text-xs text-white/40">Вариант #{idx + 1}</span>
                  <input
                    className="input-underline"
                    placeholder="Текст варианта"
                    value={choice.text}
                    onChange={(e) => updateChoice(idx, 'text', e.target.value)}
                  />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="flex flex-col gap-2">
                    <span className="text-[10px] text-white/40">Тип исхода</span>
                    <select
                      className="input-underline"
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
                  <div className="flex flex-col gap-2">
                    <span className="text-[10px] text-white/40">Данные исхода (JSON)</span>
                    <input
                      className="input-underline"
                      placeholder='{"item_id": 1, "quantity": 1}'
                      value={choice.outcome_data}
                      onChange={(e) => updateChoice(idx, 'outcome_data', e.target.value)}
                    />
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => removeChoice(idx)}
                  className="text-site-red text-xs hover:text-white transition-colors self-end"
                >
                  Удалить вариант
                </button>
              </div>
            ))}
          </div>
        );

      case 'rest':
        return (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="flex flex-col gap-2">
              <label className="text-sm text-white/70">Восстановление (%)</label>
              <input
                type="number"
                className="input-underline"
                value={form.heal_percent}
                min={0}
                max={100}
                onChange={(e) => updateField('heal_percent', Number(e.target.value))}
              />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-sm text-white/70">Ожидание (сек)</label>
              <input
                type="number"
                className="input-underline"
                value={form.wait_seconds}
                min={0}
                onChange={(e) => updateField('wait_seconds', Number(e.target.value))}
              />
            </div>
            <div className="flex flex-col gap-2">
              <label className="text-sm text-white/70">Стоимость (золото)</label>
              <input
                type="number"
                className="input-underline"
                value={form.gold_cost}
                min={0}
                onChange={(e) => updateField('gold_cost', Number(e.target.value))}
              />
            </div>
          </div>
        );

      case 'merchant':
        return (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <label className="text-sm text-white/70">Товары торговца</label>
              <button type="button" onClick={addMerchantItem} className="text-xs text-site-blue hover:text-white transition-colors">
                + Добавить товар
              </button>
            </div>
            {form.merchant_items.map((item, idx) => (
              <div key={idx} className="flex flex-wrap gap-2 items-center bg-white/[0.03] rounded-card p-3">
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-white/40">ID предмета</span>
                  <input
                    type="number"
                    className="input-underline !w-24"
                    value={item.item_id}
                    onChange={(e) => updateMerchantItem(idx, 'item_id', Number(e.target.value))}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-white/40">Цена</span>
                  <input
                    type="number"
                    className="input-underline !w-24"
                    value={item.price}
                    min={0}
                    onChange={(e) => updateMerchantItem(idx, 'price', Number(e.target.value))}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] text-white/40">Запас</span>
                  <input
                    type="number"
                    className="input-underline !w-20"
                    value={item.stock}
                    min={0}
                    onChange={(e) => updateMerchantItem(idx, 'stock', Number(e.target.value))}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => removeMerchantItem(idx)}
                  className="text-site-red text-xs hover:text-white transition-colors mt-4"
                >
                  Удалить
                </button>
              </div>
            ))}
          </div>
        );

      case 'teleport':
        return (
          <div className="flex flex-col gap-2">
            <label className="text-sm text-white/70">Целевая комната</label>
            <select
              className="input-underline"
              value={form.target_room_id ?? ''}
              onChange={(e) => updateField('target_room_id', e.target.value ? Number(e.target.value) : null)}
            >
              <option value="" className="bg-site-dark text-white">— Выберите комнату —</option>
              {rooms
                .filter((r) => !(isEdit && r.id === Number(roomId)))
                .map((r) => (
                  <option key={r.id} value={r.id} className="bg-site-dark text-white">
                    {r.name} ({r.room_type})
                  </option>
                ))}
            </select>
          </div>
        );

      case 'fork':
      case 'deadend':
        return (
          <p className="text-white/40 text-sm">Для этого типа комнаты дополнительных настроек нет.</p>
        );

      default:
        return null;
    }
  };

  return (
    <div className="w-full max-w-[900px] mx-auto flex flex-col gap-6">
      <button
        onClick={() => navigate(`/admin/dungeons/${dungeonId}`)}
        className="text-sm text-white/50 hover:text-site-blue transition-colors duration-200 self-start"
      >
        &larr; Назад к подземелью
      </button>

      <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">
        {isEdit ? 'Редактировать комнату' : 'Создать комнату'}
      </h1>

      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        {/* Basic fields */}
        <div className="gray-bg p-4 sm:p-6 flex flex-col gap-4">
          <h2 className="text-white text-sm font-medium uppercase tracking-[0.06em] mb-2">Основные параметры</h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <label className="text-sm text-white/70">Тип комнаты *</label>
              <select
                className="input-underline"
                value={form.room_type}
                onChange={(e) => updateField('room_type', e.target.value as RoomType)}
              >
                {ROOM_TYPES.map((rt) => (
                  <option key={rt.value} value={rt.value} className="bg-site-dark text-white">
                    {rt.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-sm text-white/70">Порядок сортировки</label>
              <input
                type="number"
                className="input-underline"
                value={form.sort_order}
                onChange={(e) => updateField('sort_order', Number(e.target.value))}
              />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-sm text-white/70">Название *</label>
            <input
              className="input-underline"
              placeholder="Зал стражей"
              value={form.name}
              onChange={(e) => updateField('name', e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-sm text-white/70">Описание *</label>
            <textarea
              className="textarea-bordered"
              rows={3}
              placeholder="Тёмный зал с колоннами..."
              value={form.description}
              onChange={(e) => updateField('description', e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-sm text-white/70">URL изображения</label>
            <input
              className="input-underline"
              placeholder="https://..."
              value={form.image_url}
              onChange={(e) => updateField('image_url', e.target.value)}
            />
          </div>

          <div className="flex flex-wrap gap-6">
            <label className="flex items-center gap-2 text-sm text-white cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_entrance}
                onChange={(e) => updateField('is_entrance', e.target.checked)}
                className="accent-gold w-4 h-4"
              />
              Вход в подземелье
            </label>
            <label className="flex items-center gap-2 text-sm text-white cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_boss_room}
                onChange={(e) => updateField('is_boss_room', e.target.checked)}
                className="accent-gold w-4 h-4"
              />
              Комната босса
            </label>
            <label className="flex items-center gap-2 text-sm text-white cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_mana_core_room}
                onChange={(e) => updateField('is_mana_core_room', e.target.checked)}
                className="accent-gold w-4 h-4"
              />
              Комната Ядра маны
            </label>
          </div>
        </div>

        {/* Dynamic config */}
        <div className="gray-bg p-4 sm:p-6 flex flex-col gap-4">
          <h2 className="text-white text-sm font-medium uppercase tracking-[0.06em] mb-2">
            Настройки типа: {ROOM_TYPES.find((r) => r.value === form.room_type)?.label}
          </h2>
          {renderConfigFields()}
        </div>

        {/* Actions */}
        <div className="flex gap-4">
          <button type="submit" disabled={saving} className="btn-blue !text-base !px-8 !py-2">
            {saving ? 'Сохранение...' : isEdit ? 'Сохранить' : 'Создать'}
          </button>
          <button
            type="button"
            onClick={() => navigate(`/admin/dungeons/${dungeonId}`)}
            className="btn-line !text-base !px-8 !py-2"
          >
            Отмена
          </button>
        </div>
      </form>
    </div>
  );
};

export default AdminDungeonRoomForm;
