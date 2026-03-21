import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../api/api';
import useDebounce from '../../hooks/useDebounce';

/* ── Types ── */

interface QuestObjectiveForm {
  description: string;
  objective_type: string;
  target_count: number;
}

interface QuestRewardItemForm {
  item_id: number | null;
  item_name: string;
  quantity: number;
}

interface QuestFormData {
  title: string;
  description: string;
  quest_type: string;
  min_level: number;
  reward_currency: number;
  reward_exp: number;
  reward_items: QuestRewardItemForm[];
  objectives: QuestObjectiveForm[];
  is_active: boolean;
}

interface QuestListItem {
  id: number;
  title: string;
  quest_type: string;
  min_level: number;
  is_active: boolean;
  objectives_count: number;
}

interface GameItem {
  id: number;
  name: string;
  image: string | null;
  item_rarity: string;
  item_type: string;
}

interface QuestEditorProps {
  npcId: number;
  npcName: string;
  onClose: () => void;
}

const INITIAL_FORM: QuestFormData = {
  title: '',
  description: '',
  quest_type: 'standard',
  min_level: 1,
  reward_currency: 0,
  reward_exp: 0,
  reward_items: [],
  objectives: [],
  is_active: true,
};

const QUEST_TYPES = [
  { value: 'standard', label: 'Обычный' },
  { value: 'daily', label: 'Ежедневный' },
  { value: 'repeatable', label: 'Повторяемый' },
];

const OBJECTIVE_TYPES = [
  { value: 'kill', label: 'Убить' },
  { value: 'collect', label: 'Собрать' },
  { value: 'talk_to', label: 'Поговорить' },
  { value: 'visit_location', label: 'Посетить локацию' },
  { value: 'deliver', label: 'Доставить' },
  { value: 'custom', label: 'Особое' },
];

/* ── Component ── */

const QuestEditor = ({ npcId, npcName, onClose }: QuestEditorProps) => {
  const [quests, setQuests] = useState<QuestListItem[]>([]);
  const [loadingQuests, setLoadingQuests] = useState(true);

  // Editor state
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<QuestFormData>(INITIAL_FORM);
  const [editorOpen, setEditorOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  // Item search for rewards
  const [itemSearchQuery, setItemSearchQuery] = useState('');
  const [itemSearchResults, setItemSearchResults] = useState<GameItem[]>([]);
  const [searchingItems, setSearchingItems] = useState(false);
  const debouncedItemQuery = useDebounce(itemSearchQuery);

  const fetchQuests = useCallback(async () => {
    setLoadingQuests(true);
    try {
      const res = await axios.get<QuestListItem[]>(
        `${BASE_URL}/locations/admin/quests`,
        { params: { npc_id: npcId } },
      );
      setQuests(res.data);
    } catch {
      toast.error('Не удалось загрузить квесты');
    } finally {
      setLoadingQuests(false);
    }
  }, [npcId]);

  useEffect(() => {
    fetchQuests();
  }, [fetchQuests]);

  // Item search
  useEffect(() => {
    if (!debouncedItemQuery || debouncedItemQuery.length < 2) {
      setItemSearchResults([]);
      return;
    }
    const searchItems = async () => {
      setSearchingItems(true);
      try {
        const res = await axios.get<GameItem[]>(
          `${BASE_URL}/inventory/admin/items`,
          { params: { search: debouncedItemQuery, limit: 10 } },
        );
        setItemSearchResults(res.data);
      } catch {
        setItemSearchResults([]);
      } finally {
        setSearchingItems(false);
      }
    };
    searchItems();
  }, [debouncedItemQuery]);

  const openCreateForm = () => {
    setEditingId(null);
    setForm(INITIAL_FORM);
    setEditorOpen(true);
  };

  const openEditForm = async (questId: number) => {
    try {
      const res = await axios.get(`${BASE_URL}/locations/admin/quests/${questId}`);
      const q = res.data;
      setForm({
        title: q.title || '',
        description: q.description || '',
        quest_type: q.quest_type || 'standard',
        min_level: q.min_level || 1,
        reward_currency: q.reward_currency || 0,
        reward_exp: q.reward_exp || 0,
        reward_items: (q.reward_items || []).map((ri: { item_id: number; item_name: string; quantity: number }) => ({
          item_id: ri.item_id,
          item_name: ri.item_name || `Предмет #${ri.item_id}`,
          quantity: ri.quantity || 1,
        })),
        objectives: (q.objectives || []).map((obj: { description: string; objective_type: string; target_count: number }) => ({
          description: obj.description || '',
          objective_type: obj.objective_type || 'custom',
          target_count: obj.target_count || 1,
        })),
        is_active: q.is_active !== false,
      });
      setEditingId(questId);
      setEditorOpen(true);
    } catch {
      toast.error('Не удалось загрузить данные квеста');
    }
  };

  const handleDeleteQuest = async (questId: number) => {
    if (!window.confirm('Удалить квест? Это действие нельзя отменить.')) return;
    try {
      await axios.delete(`${BASE_URL}/locations/admin/quests/${questId}`);
      toast.success('Квест удалён');
      setQuests((prev) => prev.filter((q) => q.id !== questId));
      if (editingId === questId) {
        setEditorOpen(false);
        setEditingId(null);
      }
    } catch {
      toast.error('Не удалось удалить квест');
    }
  };

  /* ── Form handlers ── */

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) => {
    const { name, value, type } = e.target;
    if (type === 'checkbox') {
      setForm((prev) => ({
        ...prev,
        [name]: (e.target as HTMLInputElement).checked,
      }));
    } else {
      setForm((prev) => ({
        ...prev,
        [name]: type === 'number' ? (value === '' ? 0 : Number(value)) : value,
      }));
    }
  };

  /* ── Objectives ── */

  const addObjective = () => {
    setForm((prev) => ({
      ...prev,
      objectives: [...prev.objectives, { description: '', objective_type: 'kill', target_count: 1 }],
    }));
  };

  const removeObjective = (index: number) => {
    setForm((prev) => ({
      ...prev,
      objectives: prev.objectives.filter((_, i) => i !== index),
    }));
  };

  const updateObjective = (index: number, field: keyof QuestObjectiveForm, value: string | number) => {
    setForm((prev) => ({
      ...prev,
      objectives: prev.objectives.map((obj, i) =>
        i === index ? { ...obj, [field]: value } : obj,
      ),
    }));
  };

  /* ── Reward items ── */

  const addRewardItem = (item: GameItem) => {
    if (form.reward_items.some((ri) => ri.item_id === item.id)) {
      toast.error('Предмет уже добавлен');
      return;
    }
    setForm((prev) => ({
      ...prev,
      reward_items: [...prev.reward_items, { item_id: item.id, item_name: item.name, quantity: 1 }],
    }));
    setItemSearchQuery('');
    setItemSearchResults([]);
  };

  const removeRewardItem = (index: number) => {
    setForm((prev) => ({
      ...prev,
      reward_items: prev.reward_items.filter((_, i) => i !== index),
    }));
  };

  const updateRewardItemQuantity = (index: number, quantity: number) => {
    setForm((prev) => ({
      ...prev,
      reward_items: prev.reward_items.map((ri, i) =>
        i === index ? { ...ri, quantity: Math.max(1, quantity) } : ri,
      ),
    }));
  };

  /* ── Save ── */

  const handleSave = async () => {
    if (!form.title.trim()) {
      toast.error('Название квеста обязательно');
      return;
    }

    const payload = {
      npc_id: npcId,
      title: form.title.trim(),
      description: form.description.trim(),
      quest_type: form.quest_type,
      min_level: form.min_level,
      reward_currency: form.reward_currency,
      reward_exp: form.reward_exp,
      reward_items: form.reward_items
        .filter((ri) => ri.item_id !== null)
        .map((ri) => ({ item_id: ri.item_id, quantity: ri.quantity })),
      objectives: form.objectives.map((obj) => ({
        description: obj.description,
        objective_type: obj.objective_type,
        target_count: obj.target_count,
      })),
      is_active: form.is_active,
    };

    setSaving(true);
    try {
      if (editingId) {
        await axios.put(`${BASE_URL}/locations/admin/quests/${editingId}`, payload);
        toast.success('Квест обновлён');
      } else {
        await axios.post(`${BASE_URL}/locations/admin/quests`, payload);
        toast.success('Квест создан');
      }
      setEditorOpen(false);
      setEditingId(null);
      fetchQuests();
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось сохранить квест';
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  /* ── Render ── */

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        <button
          onClick={onClose}
          className="text-white/50 hover:text-white transition-colors flex items-center gap-1 text-sm"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          Назад к НПС
        </button>
        <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase tracking-[0.06em]">
          Квесты: {npcName}
        </h2>
        <button className="btn-blue !text-sm !px-5 !py-2 sm:ml-auto" onClick={openCreateForm}>
          Создать квест
        </button>
      </div>

      {/* Quests list */}
      {!editorOpen && (
        <div className="gray-bg p-4 sm:p-6">
          {loadingQuests ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
            </div>
          ) : quests.length === 0 ? (
            <p className="text-center text-white/50 text-sm py-6">Квесты не найдены</p>
          ) : (
            <div className="flex flex-col gap-3">
              {quests.map((quest) => (
                <div
                  key={quest.id}
                  className="flex flex-col sm:flex-row items-start sm:items-center gap-3 bg-white/[0.03] rounded-card p-4"
                >
                  <div className="flex flex-col gap-1 min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-white text-sm font-medium">{quest.title}</span>
                      <span className="px-2 py-0.5 rounded-full bg-gold/20 text-gold text-[10px] font-medium uppercase">
                        {QUEST_TYPES.find((t) => t.value === quest.quest_type)?.label || quest.quest_type}
                      </span>
                      {!quest.is_active && (
                        <span className="px-2 py-0.5 rounded-full bg-site-red/20 text-site-red text-[10px] font-medium uppercase">
                          Неактивен
                        </span>
                      )}
                    </div>
                    <span className="text-white/40 text-xs">
                      ID: {quest.id} | Мин. уровень: {quest.min_level} | Задач: {quest.objectives_count}
                    </span>
                  </div>
                  <div className="flex gap-3 shrink-0">
                    <button
                      onClick={() => openEditForm(quest.id)}
                      className="text-sm text-white hover:text-site-blue transition-colors"
                    >
                      Редактировать
                    </button>
                    <button
                      onClick={() => handleDeleteQuest(quest.id)}
                      className="text-sm text-site-red hover:text-white transition-colors"
                    >
                      Удалить
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Editor form */}
      {editorOpen && (
        <div className="gray-bg p-4 sm:p-6 flex flex-col gap-5">
          <h3 className="gold-text text-lg sm:text-xl font-medium uppercase tracking-[0.06em]">
            {editingId ? 'Редактирование квеста' : 'Новый квест'}
          </h3>

          {/* Basic fields */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
            {/* Title */}
            <label className="flex flex-col gap-1 sm:col-span-2 lg:col-span-2">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Название</span>
              <input
                name="title"
                value={form.title}
                onChange={handleChange}
                required
                className="input-underline"
                placeholder="Название квеста..."
              />
            </label>

            {/* Quest type */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Тип квеста</span>
              <select name="quest_type" value={form.quest_type} onChange={handleChange} className="input-underline">
                {QUEST_TYPES.map((t) => (
                  <option key={t.value} value={t.value} className="bg-site-dark text-white">{t.label}</option>
                ))}
              </select>
            </label>

            {/* Min level */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Мин. уровень</span>
              <input type="number" name="min_level" value={form.min_level} onChange={handleChange} min={1} className="input-underline" />
            </label>

            {/* Reward currency */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Награда (золото)</span>
              <input type="number" name="reward_currency" value={form.reward_currency} onChange={handleChange} min={0} className="input-underline" />
            </label>

            {/* Reward exp */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Награда (опыт)</span>
              <input type="number" name="reward_exp" value={form.reward_exp} onChange={handleChange} min={0} className="input-underline" />
            </label>
          </div>

          {/* Description */}
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Описание</span>
            <textarea
              name="description"
              value={form.description}
              onChange={handleChange}
              rows={3}
              className="textarea-bordered text-sm"
              placeholder="Описание квеста..."
            />
          </label>

          {/* Active checkbox */}
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              name="is_active"
              checked={form.is_active}
              onChange={handleChange}
              className="w-4 h-4 accent-gold"
            />
            <span className="text-white/70 text-sm">Активен</span>
          </label>

          {/* ── Objectives ── */}
          <div className="flex flex-col gap-3">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Задачи ({form.objectives.length})
            </span>

            {form.objectives.map((obj, idx) => (
              <div
                key={idx}
                className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 bg-white/[0.03] rounded-card p-3"
              >
                {/* Description */}
                <input
                  value={obj.description}
                  onChange={(e) => updateObjective(idx, 'description', e.target.value)}
                  className="input-underline !text-sm flex-1"
                  placeholder="Описание задачи..."
                />

                {/* Type */}
                <select
                  value={obj.objective_type}
                  onChange={(e) => updateObjective(idx, 'objective_type', e.target.value)}
                  className="input-underline !text-sm max-w-[160px]"
                >
                  {OBJECTIVE_TYPES.map((t) => (
                    <option key={t.value} value={t.value} className="bg-site-dark text-white">{t.label}</option>
                  ))}
                </select>

                {/* Target count */}
                <input
                  type="number"
                  value={obj.target_count}
                  onChange={(e) => updateObjective(idx, 'target_count', Number(e.target.value) || 1)}
                  min={1}
                  className="input-underline !text-sm max-w-[80px]"
                  title="Количество"
                />

                {/* Remove */}
                <button
                  onClick={() => removeObjective(idx)}
                  className="text-site-red hover:text-white transition-colors p-1 shrink-0 self-center"
                  title="Удалить задачу"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}

            <button
              onClick={addObjective}
              className="text-sm text-site-blue hover:text-white transition-colors self-start"
            >
              + Добавить задачу
            </button>
          </div>

          {/* ── Reward items ── */}
          <div className="flex flex-col gap-3">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Предметы-награды ({form.reward_items.length})
            </span>

            {form.reward_items.map((ri, idx) => (
              <div
                key={idx}
                className="flex items-center gap-3 bg-white/[0.03] rounded-card p-3"
              >
                <span className="text-white text-sm flex-1 min-w-0 truncate">{ri.item_name}</span>
                <label className="flex items-center gap-1 shrink-0">
                  <span className="text-white/50 text-xs">x</span>
                  <input
                    type="number"
                    value={ri.quantity}
                    onChange={(e) => updateRewardItemQuantity(idx, Number(e.target.value))}
                    min={1}
                    className="input-underline !text-sm w-16"
                  />
                </label>
                <button
                  onClick={() => removeRewardItem(idx)}
                  className="text-site-red hover:text-white transition-colors p-1 shrink-0"
                  title="Удалить"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}

            {/* Item search */}
            <div className="relative max-w-sm">
              <input
                value={itemSearchQuery}
                onChange={(e) => setItemSearchQuery(e.target.value)}
                className="input-underline !text-sm"
                placeholder="Найти предмет для награды..."
              />
              {(itemSearchResults.length > 0 || searchingItems) && itemSearchQuery.length >= 2 && (
                <div className="absolute top-full left-0 right-0 z-50 mt-1 dropdown-menu max-h-48 overflow-y-auto gold-scrollbar">
                  {searchingItems ? (
                    <div className="flex items-center justify-center py-3">
                      <div className="w-4 h-4 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
                    </div>
                  ) : (
                    itemSearchResults.map((item) => (
                      <button
                        key={item.id}
                        onClick={() => addRewardItem(item)}
                        className="dropdown-item w-full text-left flex items-center gap-2"
                      >
                        {item.image ? (
                          <img src={item.image} alt={item.name} className="w-6 h-6 rounded-full object-cover shrink-0" />
                        ) : (
                          <span className="w-6 h-6 rounded-full bg-white/10 shrink-0" />
                        )}
                        <span className="truncate">{item.name}</span>
                        <span className="text-white/30 text-xs ml-auto shrink-0">#{item.id}</span>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 pt-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="btn-blue !text-base !px-8 !py-2 disabled:opacity-50"
            >
              {saving ? 'Сохранение...' : editingId ? 'Сохранить' : 'Создать'}
            </button>
            <button
              onClick={() => {
                setEditorOpen(false);
                setEditingId(null);
              }}
              className="btn-line !w-auto !px-8"
            >
              Отмена
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default QuestEditor;
