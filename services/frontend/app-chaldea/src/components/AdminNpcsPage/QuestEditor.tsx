import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../api/api';
import useDebounce from '../../hooks/useDebounce';
import { useCurrency } from '../../hooks/useCurrency';
import ReputationTierSelect from '../Admin/ReputationPage/ReputationTierSelect';
import { DEFAULT_QUEST_REPUTATION } from '../../api/reputationAdmin';
import { QUEST_FAME_REWARD_DEFAULT, QUEST_FAME_REWARD_MAX } from '../../api/shadowAdmin';
import { useFameTierOptions } from '../Admin/ReputationPage/useShadowRefs';
import { EntityPicker } from '../Admin/DungeonsPage/editor/pickers';
import { useFactionOptions } from '../Admin/FactionsPage/adminShared';
import { useDirtyReport, useOpenSnapshotDirty } from '../Admin/ExpandableList/useDirtyReport';
import { FACTION_LIMITS, adminGetFaction, type FactionRankAdmin } from '../../api/factions';
import { apiErrorMessage } from '../../api/errors';

/* ── Types ── */

interface QuestObjectiveForm {
  description: string;
  objective_type: string;
  target_count: number;
  target_id: number | null;
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
  /** FEAT-197: typed text; '' = the default weight (action «Выполнено задание») */
  reputation_reward: string;
  /** FEAT-197: tier gate code, null = none */
  min_reputation_tier: string | null;
  /** FEAT-199: typed text; '' = the default fame (shadow settings «за задание по умолчанию») */
  fame_reward: string;
  /** FEAT-199: fame tier gate code, null = none */
  min_fame_tier: string | null;
  /** FEAT-205: members-only quest of this faction (null = anyone) */
  faction_id: number | null;
  /** FEAT-205: the rank needed inside `faction_id` (null = any member) */
  min_faction_rank_id: number | null;
  /** FEAT-205: faction points for completing; points typed as text (±) */
  faction_points_rewards: { faction_id: number | null; points: string }[];
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
  onClose?: () => void;
  /** FEAT-208: rendered inside the NPC panel — no own title / back link */
  embedded?: boolean;
  /** FEAT-208: reports an open quest form with unsaved changes */
  onDirtyChange?: (dirty: boolean) => void;
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
  reputation_reward: '',
  min_reputation_tier: null,
  fame_reward: '',
  min_fame_tier: null,
  faction_id: null,
  min_faction_rank_id: null,
  faction_points_rewards: [],
};

const UNSIGNED_INT_RE = /^\d*$/;

const REPUTATION_REWARD_LIMIT = 1000;
const SIGNED_INT_RE = /^-?\d*$/;

const QUEST_TYPES = [
  { value: 'standard', label: 'Обычный' },
  { value: 'daily', label: 'Ежедневный' },
  { value: 'repeatable', label: 'Повторяемый' },
];

const OBJECTIVE_TYPES = [
  { value: 'kill', label: 'Убить' },
  { value: 'kill_mob', label: 'Убить моба (конкретного)' },
  { value: 'kill_mob_any', label: 'Убить любого моба' },
  { value: 'kill_mob_tier', label: 'Убить моба тира' },
  { value: 'defeat_npc', label: 'Победить НПС' },
  { value: 'defeat_any', label: 'Победить любого противника' },
  { value: 'collect', label: 'Собрать' },
  { value: 'talk_to', label: 'Поговорить' },
  { value: 'visit_location', label: 'Посетить локацию' },
  { value: 'write_posts', label: 'Написать посты' },
  { value: 'write_post_in_location', label: 'Написать пост в локации' },
  { value: 'write_chars', label: 'Написать символов (суммарно)' },
  { value: 'write_chars_in_location', label: 'Написать символов в локации' },
  { value: 'complete_quest', label: 'Завершить квест' },
  { value: 'deliver', label: 'Доставить' },
  { value: 'custom', label: 'Особое' },
];

type TargetKind = 'mob' | 'npc' | 'location' | 'quest' | 'item';

/** Which picker an objective type needs for its target (null = no target or a fixed list). */
const targetKind = (objectiveType: string): TargetKind | null => {
  switch (objectiveType) {
    case 'kill_mob':
      return 'mob';
    case 'defeat_npc':
    case 'talk_to':
      return 'npc';
    case 'visit_location':
    case 'write_post_in_location':
    case 'write_chars_in_location':
      return 'location';
    case 'complete_quest':
      return 'quest';
    case 'collect':
      return 'item';
    default:
      return null;
  }
};

/* ── Component ── */

const QuestEditor = ({ npcId, npcName, onClose, embedded = false, onDirtyChange }: QuestEditorProps) => {
  const { forms } = useCurrency();
  const fameTiers = useFameTierOptions();
  // FEAT-205: faction fields (the list needs factions:read; without it the block explains why it is empty).
  const { factions, error: factionsError } = useFactionOptions();
  const [factionRanks, setFactionRanks] = useState<FactionRankAdmin[]>([]);
  const [quests, setQuests] = useState<QuestListItem[]>([]);
  const [loadingQuests, setLoadingQuests] = useState(true);

  // Editor state
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<QuestFormData>(INITIAL_FORM);
  const [editorOpen, setEditorOpen] = useState(false);
  const [openSeq, setOpenSeq] = useState(0);
  const [saving, setSaving] = useState(false);

  useDirtyReport(useOpenSnapshotDirty(editorOpen, form, openSeq), onDirtyChange);

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
          `${BASE_URL}/inventory/items`,
          { params: { q: debouncedItemQuery, page: 1, page_size: 10 } },
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

  // Ranks of the chosen faction for the «Мин. звание» select.
  useEffect(() => {
    if (!form.faction_id) {
      setFactionRanks([]);
      return;
    }
    let cancelled = false;
    adminGetFaction(form.faction_id)
      .then((d) => {
        if (!cancelled) setFactionRanks([...d.ranks].sort((a, b) => a.sort_order - b.sort_order));
      })
      .catch((e) => {
        if (!cancelled) toast.error(apiErrorMessage(e, 'Не удалось загрузить звания фракции'));
      });
    return () => {
      cancelled = true;
    };
  }, [form.faction_id]);

  const openCreateForm = () => {
    setEditingId(null);
    setForm(INITIAL_FORM);
    setEditorOpen(true);
    setOpenSeq((n) => n + 1);
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
        objectives: (q.objectives || []).map((obj: { description: string; objective_type: string; target_count: number; target_id?: number | null }) => ({
          description: obj.description || '',
          objective_type: obj.objective_type || 'custom',
          target_count: obj.target_count || 1,
          target_id: obj.target_id ?? null,
        })),
        is_active: q.is_active !== false,
        reputation_reward: q.reputation_reward == null ? '' : String(q.reputation_reward),
        min_reputation_tier: q.min_reputation_tier ?? null,
        fame_reward: q.fame_reward == null ? '' : String(q.fame_reward),
        min_fame_tier: q.min_fame_tier ?? null,
        faction_id: q.faction_id ?? null,
        min_faction_rank_id: q.min_faction_rank_id ?? null,
        faction_points_rewards: (q.faction_points_rewards || []).map((r: { faction_id: number; points: number }) => ({
          faction_id: r.faction_id,
          points: String(r.points),
        })),
      });
      setEditingId(questId);
      setEditorOpen(true);
      setOpenSeq((n) => n + 1);
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

  const setObjectiveTarget = (index: number, id: number | null) => {
    setForm((prev) => ({
      ...prev,
      objectives: prev.objectives.map((obj, i) => (i === index ? { ...obj, target_id: id } : obj)),
    }));
  };

  const addObjective = () => {
    setForm((prev) => ({
      ...prev,
      objectives: [...prev.objectives, { description: '', objective_type: 'kill', target_count: 1, target_id: null }],
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
        i !== index
          ? obj
          // a new type means a different kind of target: the old id would point at the wrong thing
          : field === 'objective_type' && value !== obj.objective_type
            ? { ...obj, objective_type: String(value), target_id: null }
            : { ...obj, [field]: value },
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
    const reputationText = form.reputation_reward.trim();
    const reputationReward = reputationText === '' ? null : Number(reputationText);
    if (
      reputationReward !== null &&
      (!Number.isInteger(reputationReward) || Math.abs(reputationReward) > REPUTATION_REWARD_LIMIT)
    ) {
      toast.error(`Репутация за задание — целое число от −${REPUTATION_REWARD_LIMIT} до ${REPUTATION_REWARD_LIMIT}`);
      return;
    }
    const fameText = form.fame_reward.trim();
    const fameReward = fameText === '' ? null : Number(fameText);
    if (fameReward !== null && (!Number.isInteger(fameReward) || fameReward < 0 || fameReward > QUEST_FAME_REWARD_MAX)) {
      toast.error(`Слава за задание — целое число от 0 до ${QUEST_FAME_REWARD_MAX}`);
      return;
    }

    const factionPoints: { faction_id: number; points: number }[] = [];
    for (const row of form.faction_points_rewards) {
      if (row.faction_id == null) {
        toast.error('Очки фракции: выберите фракцию в каждой строке');
        return;
      }
      const pts = Number(row.points.trim());
      if (row.points.trim() === '' || !Number.isInteger(pts) || pts === 0 || Math.abs(pts) > FACTION_LIMITS.questPointsMax) {
        toast.error(`Очки фракции — целое число от −${FACTION_LIMITS.questPointsMax} до ${FACTION_LIMITS.questPointsMax}, не 0`);
        return;
      }
      if (factionPoints.some((fp) => fp.faction_id === row.faction_id)) {
        toast.error('Очки фракции: одна фракция указана дважды');
        return;
      }
      factionPoints.push({ faction_id: row.faction_id, points: pts });
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
        target_id: obj.target_id,
      })),
      is_active: form.is_active,
      reputation_reward: reputationReward,
      min_reputation_tier: form.min_reputation_tier,
      fame_reward: fameReward,
      min_fame_tier: form.min_fame_tier,
      faction_id: form.faction_id,
      min_faction_rank_id: form.faction_id ? form.min_faction_rank_id : null,
      faction_points_rewards: factionPoints.length ? factionPoints : null,
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
      // 422 validation comes as a list — apiErrorMessage handles both shapes.
      toast.error(apiErrorMessage(err, 'Не удалось сохранить квест'));
    } finally {
      setSaving(false);
    }
  };

  /* ── Render ── */

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        {!embedded && (
          <>
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
          </>
        )}
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
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Награда ({forms.name.toLowerCase()})</span>
              <input type="number" name="reward_currency" value={form.reward_currency} onChange={handleChange} min={0} className="input-underline" />
            </label>

            {/* Reward exp */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Награда (опыт)</span>
              <input type="number" name="reward_exp" value={form.reward_exp} onChange={handleChange} min={0} className="input-underline" />
            </label>

            {/* FEAT-197: reputation weight + tier gate */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Репутация за задание</span>
              <input
                inputMode="numeric"
                value={form.reputation_reward}
                onChange={(e) => {
                  const v = e.target.value;
                  if (SIGNED_INT_RE.test(v)) setForm((prev) => ({ ...prev, reputation_reward: v }));
                }}
                placeholder={`по умолчанию: ${DEFAULT_QUEST_REPUTATION}`}
                className="input-underline"
              />
              <span className="text-white/40 text-xs">В регионе квестодателя; пусто — вес по умолчанию</span>
            </label>

            <ReputationTierSelect
              value={form.min_reputation_tier}
              onChange={(code) => setForm((prev) => ({ ...prev, min_reputation_tier: code }))}
              hint="Ниже этой ступени задание нельзя взять"
            />

            {/* FEAT-199: fame reward + fame tier gate */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Слава за задание</span>
              <input
                inputMode="numeric"
                value={form.fame_reward}
                onChange={(e) => {
                  const v = e.target.value;
                  if (UNSIGNED_INT_RE.test(v)) setForm((prev) => ({ ...prev, fame_reward: v }));
                }}
                placeholder={`по умолчанию: ${QUEST_FAME_REWARD_DEFAULT}`}
                className="input-underline"
              />
              <span className="text-white/40 text-xs">Пусто — значение по умолчанию; 0 — без славы</span>
            </label>

            <label className="flex flex-col gap-1 min-w-0">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Мин. слава</span>
              <select
                value={form.min_fame_tier ?? ''}
                onChange={(e) => {
                  const code = e.target.value === '' ? null : e.target.value;
                  setForm((prev) => ({ ...prev, min_fame_tier: code }));
                }}
                className="input-underline w-full"
              >
                <option value="" className="bg-site-dark text-white">Без ограничения</option>
                {fameTiers.map((t) => (
                  <option key={t.code} value={t.code} className="bg-site-dark text-white">{t.name}</option>
                ))}
                {form.min_fame_tier && !fameTiers.some((t) => t.code === form.min_fame_tier) && (
                  <option value={form.min_fame_tier} className="bg-site-dark text-white">{form.min_fame_tier}</option>
                )}
              </select>
              <span className="text-white/40 text-xs">Ниже этой ступени славы задание нельзя взять</span>
            </label>
          </div>

          {/* FEAT-205: faction quest + faction points */}
          <div className="flex flex-col gap-3 bg-white/[0.03] rounded-card p-3 sm:p-4">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Фракция</span>
            {factionsError ? (
              <p className="text-site-red text-xs">{factionsError}</p>
            ) : (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <label className="flex flex-col gap-1 min-w-0">
                    <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Только для членов фракции</span>
                    <select
                      value={form.faction_id ?? ''}
                      onChange={(e) => {
                        const id = e.target.value === '' ? null : Number(e.target.value);
                        setForm((prev) => ({ ...prev, faction_id: id, min_faction_rank_id: null }));
                      }}
                      className="input-underline w-full"
                    >
                      <option value="" className="bg-site-dark text-white">— Для всех —</option>
                      {factions.map((f) => (
                        <option key={f.id} value={f.id} className="bg-site-dark text-white">
                          {f.is_secret ? `${f.name} (тайная)` : f.name}
                        </option>
                      ))}
                    </select>
                    <span className="text-white/40 text-xs">Не-члены видят задание закрытым; задания тайной фракции им не видны вовсе</span>
                  </label>
                  <label className="flex flex-col gap-1 min-w-0">
                    <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Мин. звание</span>
                    <select
                      value={form.min_faction_rank_id ?? ''}
                      disabled={!form.faction_id}
                      onChange={(e) => {
                        const id = e.target.value === '' ? null : Number(e.target.value);
                        setForm((prev) => ({ ...prev, min_faction_rank_id: id }));
                      }}
                      className="input-underline w-full disabled:opacity-50"
                    >
                      <option value="" className="bg-site-dark text-white">Любой участник</option>
                      {factionRanks.map((r, i) => (
                        <option key={r.id} value={r.id} className="bg-site-dark text-white">
                          {i + 1}. {r.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <div className="flex flex-col gap-2">
                  <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                    Очки фракций за выполнение ({form.faction_points_rewards.length}/{FACTION_LIMITS.questRewardsMax})
                  </span>
                  {form.faction_points_rewards.map((row, idx) => (
                    <div key={idx} className="flex flex-col sm:flex-row sm:items-center gap-2">
                      <select
                        value={row.faction_id ?? ''}
                        onChange={(e) => {
                          const id = e.target.value === '' ? null : Number(e.target.value);
                          setForm((prev) => ({
                            ...prev,
                            faction_points_rewards: prev.faction_points_rewards.map((r, i) => (i === idx ? { ...r, faction_id: id } : r)),
                          }));
                        }}
                        className="input-underline !text-sm flex-1 min-w-0"
                      >
                        <option value="" className="bg-site-dark text-white">— Фракция —</option>
                        {factions.map((f) => (
                          <option key={f.id} value={f.id} className="bg-site-dark text-white">{f.name}</option>
                        ))}
                      </select>
                      <div className="flex items-center gap-2">
                        <input
                          inputMode="numeric"
                          value={row.points}
                          onChange={(e) => {
                            const v = e.target.value;
                            if (!SIGNED_INT_RE.test(v)) return;
                            setForm((prev) => ({
                              ...prev,
                              faction_points_rewards: prev.faction_points_rewards.map((r, i) => (i === idx ? { ...r, points: v } : r)),
                            }));
                          }}
                          placeholder="±очки"
                          className="input-underline !text-sm w-24"
                        />
                        <button
                          type="button"
                          onClick={() =>
                            setForm((prev) => ({
                              ...prev,
                              faction_points_rewards: prev.faction_points_rewards.filter((_, i) => i !== idx),
                            }))
                          }
                          className="text-site-red hover:text-white transition-colors p-1"
                          title="Убрать"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  ))}
                  {form.faction_points_rewards.length < FACTION_LIMITS.questRewardsMax && (
                    <button
                      type="button"
                      onClick={() =>
                        setForm((prev) => ({
                          ...prev,
                          faction_points_rewards: [...prev.faction_points_rewards, { faction_id: null, points: '' }],
                        }))
                      }
                      className="text-sm text-site-blue hover:text-white transition-colors self-start"
                    >
                      + Добавить очки фракции
                    </button>
                  )}
                  <span className="text-white/40 text-xs">
                    Начисляются только тем, кто состоит во фракции; минус — штраф. Получив очки, персонаж теряет часть очков
                    во враждебных фракциях.
                  </span>
                </div>
              </>
            )}
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

                {/* Target (contextual by type): searched by name or id */}
                {obj.objective_type === 'kill_mob_tier' && (
                  <select
                    value={obj.target_id ?? ''}
                    onChange={(e) => setObjectiveTarget(idx, e.target.value ? Number(e.target.value) : null)}
                    className="input-underline !text-sm sm:max-w-[160px]"
                  >
                    <option value="" className="bg-site-dark text-white">— Тир —</option>
                    <option value={1} className="bg-site-dark text-white">Обычный (normal)</option>
                    <option value={2} className="bg-site-dark text-white">Элитный (elite)</option>
                    <option value={3} className="bg-site-dark text-white">Босс (boss)</option>
                  </select>
                )}

                {targetKind(obj.objective_type) && (
                  <div className="w-full sm:w-[220px] sm:shrink-0 min-w-0">
                    <EntityPicker
                      key={obj.objective_type}
                      kind={targetKind(obj.objective_type)!}
                      value={obj.target_id}
                      onChange={(id) => setObjectiveTarget(idx, id)}
                    />
                  </div>
                )}

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
