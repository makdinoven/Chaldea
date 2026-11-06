import { useState } from 'react';
import toast from 'react-hot-toast';
import { Award, X } from 'lucide-react';
import {
  FACTION_LIMITS,
  FACTION_PASSIVE_LIMITS,
  FACTION_QM_DISCOUNT_MAX,
  FACTION_RANK_MARKS_MAX,
  adminCreateRank,
  adminUpdateRank,
  type FactionRankAdmin,
  type FactionModifiers,
  type FactionRankInput,
} from '../../../api/factions';
import { FACTION_PASSIVE_KEYS, FACTION_PASSIVE_OPTIONS } from '../../../constants/attributeBonusOptions';
import { apiErrorMessage } from '../../../api/errors';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import { EntityPicker } from '../DungeonsPage/editor/pickers';
import { FIELD, INT_RE, LABEL, NonRepeatableQuestSelect, OPTION, SIGNED_INT_RE, TitleSelect, toInt } from './adminShared';

interface RankFormModalProps {
  factionId: number;
  /** null → a new rank (appended to the top of the ladder) */
  rank: FactionRankAdmin | null;
  /** The entry rank: its conditions are ignored, so the fields are hidden. */
  isEntry: boolean;
  canEdit: boolean;
  onClose: () => void;
  onSaved: () => void;
}

interface ItemRow {
  item_id: number | null;
  quantity: string;
}

/** FEAT-207: one modifier of the rank passive. */
interface ModifierRow {
  key: string;
  value: string;
}

const PASSIVE_GROUPS = [...new Set(FACTION_PASSIVE_OPTIONS.map((o) => o.group ?? ''))];

/** Rows → `{key: int}`; a string = a Russian validation error. */
const modifiersBody = (rows: ModifierRow[]): FactionModifiers | string => {
  const out: FactionModifiers = {};
  for (const r of rows) {
    if (!r.key) return 'Пассивка: выберите характеристику в каждой строке';
    if (!FACTION_PASSIVE_KEYS.has(r.key)) return `Пассивка: характеристика «${r.key}» не действует в бою`;
    if (r.key in out) return 'Пассивка: одна характеристика указана дважды';
    const v = toInt(r.value);
    if (v == null || v === 0 || v < FACTION_PASSIVE_LIMITS.valueMin || v > FACTION_PASSIVE_LIMITS.valueMax) {
      return `Пассивка: значение от ${FACTION_PASSIVE_LIMITS.valueMin} до ${FACTION_PASSIVE_LIMITS.valueMax}, не 0`;
    }
    out[r.key] = v;
  }
  return out;
};

const NumberField = ({
  label,
  value,
  onChange,
  hint,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  hint?: string;
  disabled: boolean;
}) => (
  <label className="flex flex-col gap-1 min-w-0">
    <span className={LABEL}>{label}</span>
    <input
      inputMode="numeric"
      value={value}
      disabled={disabled}
      onChange={(e) => INT_RE.test(e.target.value) && onChange(e.target.value)}
      className={FIELD}
    />
    {hint && <span className="text-white/40 text-xs">{hint}</span>}
  </label>
);

const RankFormModal = ({ factionId, rank, isEntry, canEdit, onClose, onSaved }: RankFormModalProps) => {
  const [name, setName] = useState(rank?.name ?? '');
  const [description, setDescription] = useState(rank?.description ?? '');
  const [minPoints, setMinPoints] = useState(String(rank?.min_points ?? 0));
  const [minLevel, setMinLevel] = useState(String(rank?.min_level ?? 0));
  const [questId, setQuestId] = useState<number | null>(rank?.required_quest_id ?? null);
  const [xp, setXp] = useState(String(rank?.reward_xp ?? 0));
  const [titleId, setTitleId] = useState<number | null>(rank?.reward_title_id ?? null);
  const [items, setItems] = useState<ItemRow[]>(
    (rank?.reward_items ?? []).map((i) => ({ item_id: i.item_id, quantity: String(i.quantity) })),
  );
  const [houseLocation, setHouseLocation] = useState<number | null>(rank?.reward_house_location_id ?? null);
  const [plotLocation, setPlotLocation] = useState<number | null>(rank?.reward_plot_location_id ?? null);
  const [marks, setMarks] = useState(String(rank?.reward_marks ?? 0));
  const [discount, setDiscount] = useState(String(rank?.qm_discount_pct ?? 0));
  const [passiveName, setPassiveName] = useState(rank?.passive_name ?? '');
  const [passiveDescription, setPassiveDescription] = useState(rank?.passive_description ?? '');
  const [modifiers, setModifiers] = useState<ModifierRow[]>(
    Object.entries(rank?.passive_modifiers ?? {}).map(([key, value]) => ({ key, value: String(value) })),
  );
  const [saving, setSaving] = useState(false);
  const ro = !canEdit;

  const save = async () => {
    const trimmed = name.trim();
    if (!trimmed || trimmed.length > FACTION_LIMITS.nameMax) {
      toast.error(`Название звания: от 1 до ${FACTION_LIMITS.nameMax} символов`);
      return;
    }
    const pts = toInt(minPoints) ?? 0;
    const lvl = toInt(minLevel) ?? 0;
    const rewardXp = toInt(xp) ?? 0;
    if (pts > FACTION_LIMITS.rankPointsMax) return void toast.error(`Очки: до ${FACTION_LIMITS.rankPointsMax}`);
    if (lvl > FACTION_LIMITS.rankLevelMax) return void toast.error(`Уровень: до ${FACTION_LIMITS.rankLevelMax}`);
    if (rewardXp > FACTION_LIMITS.rankXpMax) return void toast.error(`Опыт: до ${FACTION_LIMITS.rankXpMax}`);
    const rewardMarks = toInt(marks) ?? 0;
    if (rewardMarks > FACTION_RANK_MARKS_MAX) return void toast.error(`Марки за звание: от 0 до ${FACTION_RANK_MARKS_MAX}`);
    const qmDiscount = toInt(discount) ?? 0;
    if (qmDiscount > FACTION_QM_DISCOUNT_MAX) return void toast.error(`Скидка у интенданта: от 0 до ${FACTION_QM_DISCOUNT_MAX} %`);
    const rows = items.filter((r) => r.item_id != null);
    if (rows.length > FACTION_LIMITS.rankItemsMax) return void toast.error(`Предметов — не больше ${FACTION_LIMITS.rankItemsMax}`);
    const ids = rows.map((r) => r.item_id);
    if (new Set(ids).size !== ids.length) return void toast.error('Один предмет указан дважды');
    const rewardItems = [];
    for (const r of rows) {
      const q = toInt(r.quantity);
      if (q == null || q < 1 || q > FACTION_LIMITS.itemQtyMax) {
        return void toast.error(`Количество предмета: от 1 до ${FACTION_LIMITS.itemQtyMax}`);
      }
      rewardItems.push({ item_id: r.item_id as number, quantity: q });
    }
    if (modifiers.length > FACTION_PASSIVE_LIMITS.keysMax) {
      return void toast.error(`Пассивка: не больше ${FACTION_PASSIVE_LIMITS.keysMax} характеристик`);
    }
    const passiveMods = modifiersBody(modifiers);
    if (typeof passiveMods === 'string') return void toast.error(passiveMods);
    const hasPassive = Object.keys(passiveMods).length > 0;
    const pName = passiveName.trim();
    if (hasPassive && !pName) return void toast.error('Пассивка: укажите название');
    if (pName.length > FACTION_PASSIVE_LIMITS.nameMax) {
      return void toast.error(`Название пассивки: до ${FACTION_PASSIVE_LIMITS.nameMax} символов`);
    }
    if (passiveDescription.trim().length > FACTION_PASSIVE_LIMITS.descriptionMax) {
      return void toast.error(`Описание пассивки: до ${FACTION_PASSIVE_LIMITS.descriptionMax} символов`);
    }
    const body: FactionRankInput = {
      name: trimmed,
      description: description.trim() || null,
      min_points: isEntry ? 0 : pts,
      min_level: isEntry ? 0 : lvl,
      required_quest_id: isEntry ? null : questId,
      reward_xp: rewardXp,
      reward_title_id: titleId,
      reward_items: rewardItems.length ? rewardItems : null,
      reward_house_location_id: houseLocation,
      reward_plot_location_id: plotLocation,
      reward_marks: rewardMarks,
      qm_discount_pct: qmDiscount,
      passive_name: hasPassive ? pName : null,
      passive_description: hasPassive ? passiveDescription.trim() || null : null,
      passive_modifiers: hasPassive ? passiveMods : null,
    };
    setSaving(true);
    try {
      if (rank) await adminUpdateRank(rank.id, body);
      else await adminCreateRank(factionId, body);
      toast.success(rank ? 'Звание сохранено' : 'Звание добавлено');
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить звание'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalShell
      open
      onClose={onClose}
      title={rank ? `Звание «${rank.name}»` : 'Новое звание'}
      icon={<Award size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
      size="lg"
      dismissible={!saving}
      closeOnBackdrop={false}
      footer={
        <>
          <button type="button" className="btn-line w-full sm:w-auto" onClick={onClose} disabled={saving}>
            {canEdit ? 'Отмена' : 'Закрыть'}
          </button>
          {canEdit && (
            <button type="button" className="btn-blue w-full sm:w-auto disabled:opacity-50" onClick={() => void save()} disabled={saving}>
              {saving ? 'Сохранение...' : 'Сохранить'}
            </button>
          )}
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={LABEL}>Название</span>
            <input value={name} maxLength={FACTION_LIMITS.nameMax} disabled={ro} onChange={(e) => setName(e.target.value)} className={FIELD} placeholder="Рыцарь" />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={LABEL}>Описание</span>
            <textarea
              value={description}
              maxLength={FACTION_LIMITS.descriptionMax}
              disabled={ro}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="textarea-bordered text-sm"
            />
          </label>
        </div>

        <div className="flex flex-col gap-3">
          <span className="gold-text text-sm font-medium uppercase tracking-[0.06em]">Условия звания</span>
          {isEntry ? (
            <p className="text-white/50 text-xs">Это первое звание — его дают при вступлении, условия не нужны.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <NumberField label="Очки фракции от" value={minPoints} onChange={setMinPoints} disabled={ro} />
              <NumberField label="Уровень от" value={minLevel} onChange={setMinLevel} disabled={ro} />
              <NonRepeatableQuestSelect value={questId} onChange={setQuestId} disabled={ro} label="Выполнено задание" />
            </div>
          )}
        </div>

        <div className="flex flex-col gap-3">
          <span className="gold-text text-sm font-medium uppercase tracking-[0.06em]">Награды (один раз)</span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <NumberField label="Опыт" value={xp} onChange={setXp} disabled={ro} hint="Без множителя книг опыта" />
            <TitleSelect value={titleId} onChange={setTitleId} disabled={ro} />
            <NumberField
              label="Марки из казны фракции"
              value={marks}
              onChange={setMarks}
              disabled={ro}
              hint="Если в казне не хватит — запишутся в долг и выплатятся позже. Задним числом не платятся"
            />
            <NumberField
              label="Скидка у интенданта, %"
              value={discount}
              onChange={setDiscount}
              disabled={ro}
              hint={`От 0 до ${FACTION_QM_DISCOUNT_MAX} % — действует, пока у участника это звание`}
            />
            <div className="flex flex-col gap-1 min-w-0">
              <span className={LABEL}>Право на готовый дом в локации</span>
              {ro ? (
                <span className="text-white/80 text-sm">{houseLocation ? `#${houseLocation}` : '—'}</span>
              ) : (
                <EntityPicker kind="location" value={houseLocation} onChange={setHouseLocation} />
              )}
            </div>
            <div className="flex flex-col gap-1 min-w-0">
              <span className={LABEL}>Право на пустой участок в локации</span>
              {ro ? (
                <span className="text-white/80 text-sm">{plotLocation ? `#${plotLocation}` : '—'}</span>
              ) : (
                <EntityPicker kind="location" value={plotLocation} onChange={setPlotLocation} />
              )}
            </div>
          </div>
          <p className="text-white/40 text-xs">
            Право на дом / участок: игрок сам выбирает любое свободное место нужного типа в этой локации и получает его
            бесплатно; налог платит как обычно.
          </p>

          <div className="flex flex-col gap-2">
            <span className={LABEL}>
              Предметы ({items.length}/{FACTION_LIMITS.rankItemsMax})
            </span>
            {items.map((row, idx) => (
              <div key={idx} className="flex flex-col sm:flex-row sm:items-center gap-2 bg-white/[0.03] rounded-card p-2.5">
                <div className="flex-1 min-w-0">
                  {ro ? (
                    <span className="text-white/80 text-sm">#{row.item_id}</span>
                  ) : (
                    <EntityPicker
                      kind="item"
                      value={row.item_id}
                      onChange={(id) => setItems((prev) => prev.map((r, i) => (i === idx ? { ...r, item_id: id } : r)))}
                    />
                  )}
                </div>
                <label className="flex items-center gap-1.5 shrink-0">
                  <span className="text-white/50 text-xs">×</span>
                  <input
                    inputMode="numeric"
                    value={row.quantity}
                    disabled={ro}
                    onChange={(e) =>
                      INT_RE.test(e.target.value) &&
                      setItems((prev) => prev.map((r, i) => (i === idx ? { ...r, quantity: e.target.value } : r)))
                    }
                    className="input-underline !text-sm w-20"
                  />
                </label>
                {!ro && (
                  <button
                    type="button"
                    onClick={() => setItems((prev) => prev.filter((_, i) => i !== idx))}
                    className="text-site-red hover:text-white transition-colors p-1 self-end sm:self-center"
                    aria-label="Убрать предмет"
                  >
                    <X size={16} />
                  </button>
                )}
              </div>
            ))}
            {!ro && items.length < FACTION_LIMITS.rankItemsMax && (
              <button
                type="button"
                onClick={() => setItems((prev) => [...prev, { item_id: null, quantity: '1' }])}
                className="text-sm text-site-blue hover:text-white transition-colors self-start"
              >
                + Добавить предмет
              </button>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <span className="gold-text text-sm font-medium uppercase tracking-[0.06em]">Пассивка</span>
          <p className="text-white/40 text-xs">
            Действует в бою, пока участник держит это звание или выше; пассивки всех полученных званий складываются. Выход
            из фракции снимает их. Без характеристик — пассивки нет.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="flex flex-col gap-1 min-w-0">
              <span className={LABEL}>Название</span>
              <input
                value={passiveName}
                maxLength={FACTION_PASSIVE_LIMITS.nameMax}
                disabled={ro}
                onChange={(e) => setPassiveName(e.target.value)}
                className={FIELD}
                placeholder="Закалка ордена"
              />
            </label>
            <label className="flex flex-col gap-1 min-w-0">
              <span className={LABEL}>Описание для игрока</span>
              <input
                value={passiveDescription}
                maxLength={FACTION_PASSIVE_LIMITS.descriptionMax}
                disabled={ro}
                onChange={(e) => setPassiveDescription(e.target.value)}
                className={FIELD}
              />
            </label>
          </div>
          <div className="flex flex-col gap-2">
            <span className={LABEL}>
              Характеристики ({modifiers.length}/{FACTION_PASSIVE_LIMITS.keysMax})
            </span>
            {modifiers.map((row, idx) => (
              <div key={idx} className="flex items-center gap-2 bg-white/[0.03] rounded-card p-2.5 min-w-0">
                <select
                  value={row.key}
                  disabled={ro}
                  onChange={(e) => setModifiers((prev) => prev.map((r, i) => (i === idx ? { ...r, key: e.target.value } : r)))}
                  className="input-underline flex-1 min-w-0"
                  aria-label="Характеристика"
                >
                  <option value="" className={OPTION}>
                    — Характеристика —
                  </option>
                  {PASSIVE_GROUPS.map((g) => (
                    <optgroup key={g} label={g} className={OPTION}>
                      {FACTION_PASSIVE_OPTIONS.filter((o) => (o.group ?? '') === g).map((o) => (
                        <option key={o.value} value={o.value} className={OPTION}>
                          {o.label}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                  {row.key && !FACTION_PASSIVE_KEYS.has(row.key) && (
                    <option value={row.key} className={OPTION}>
                      {row.key}
                    </option>
                  )}
                </select>
                <input
                  inputMode="numeric"
                  value={row.value}
                  disabled={ro}
                  onChange={(e) =>
                    SIGNED_INT_RE.test(e.target.value) &&
                    setModifiers((prev) => prev.map((r, i) => (i === idx ? { ...r, value: e.target.value } : r)))
                  }
                  className="input-underline !text-sm w-16 sm:w-20 shrink-0"
                  placeholder="5"
                  aria-label="Значение"
                />
                {!ro && (
                  <button
                    type="button"
                    onClick={() => setModifiers((prev) => prev.filter((_, i) => i !== idx))}
                    className="text-site-red hover:text-white transition-colors p-1 shrink-0"
                    aria-label="Убрать характеристику"
                  >
                    <X size={16} />
                  </button>
                )}
              </div>
            ))}
            {!ro && modifiers.length < FACTION_PASSIVE_LIMITS.keysMax && (
              <button
                type="button"
                onClick={() => setModifiers((prev) => [...prev, { key: '', value: '' }])}
                className="text-sm text-site-blue hover:text-white transition-colors self-start"
              >
                + Добавить характеристику
              </button>
            )}
            <span className="text-white/40 text-xs">
              Целые числа от {FACTION_PASSIVE_LIMITS.valueMin} до {FACTION_PASSIVE_LIMITS.valueMax}, не 0. Только боевые
              характеристики: ресурсы, харизма и скрытность в бою не действуют.
            </span>
          </div>
        </div>
      </div>
    </ModalShell>
  );
};

export default RankFormModal;
