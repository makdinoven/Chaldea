import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { ArrowLeft } from 'lucide-react';
import {
  FACTION_LIMITS,
  adminCreateFaction,
  adminGetFaction,
  adminUpdateFaction,
  type FactionAdminDetail,
  type FactionInput,
} from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import ImageField from '../../pages/EpisodesPage/ImageField';
import { EntityListPicker, EntityPicker } from '../DungeonsPage/editor/pickers';
import { FIELD, INT_RE, LABEL, SIGNED_INT_RE, SubTabs, toInt } from './adminShared';
import FactionEconomyPanel from './FactionEconomyPanel';
import RanksEditor from './RanksEditor';
import ConditionsEditor from './ConditionsEditor';
import TerritoryTab from './TerritoryTab';
import EnemiesEditor from './EnemiesEditor';
import OutlawRegionsEditor from './OutlawRegionsEditor';

type Section = 'main' | 'territory' | 'economy';

interface FactionEditorProps {
  /** null → a new faction */
  factionId: number | null;
  canEdit: boolean;
  canDelete: boolean;
  onClose: () => void;
  onCreated: (id: number) => void;
}

interface FormState {
  name: string;
  description: string;
  emblem_url: string | null;
  hq_location_id: number | null;
  leader_npc_ids: number[];
  member_limit: string;
  sort_order: string;
  is_invite_only: boolean;
  is_secret: boolean;
  is_active: boolean;
}

const EMPTY_FORM: FormState = {
  name: '',
  description: '',
  emblem_url: null,
  hq_location_id: null,
  leader_npc_ids: [],
  member_limit: '',
  sort_order: '0',
  is_invite_only: false,
  is_secret: false,
  is_active: false,
};

const formFrom = (d: FactionAdminDetail): FormState => ({
  name: d.name,
  description: d.description ?? '',
  emblem_url: d.emblem_url,
  hq_location_id: d.hq_location_id,
  leader_npc_ids: d.leader_npc_ids ?? [],
  member_limit: d.member_limit == null ? '' : String(d.member_limit),
  sort_order: String(d.sort_order ?? 0),
  is_invite_only: d.is_invite_only,
  is_secret: d.is_secret,
  is_active: d.is_active,
});

const Toggle = ({
  checked,
  onChange,
  label,
  hint,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint: string;
  disabled: boolean;
}) => (
  <label className="flex items-start gap-2 cursor-pointer select-none">
    <input
      type="checkbox"
      checked={checked}
      disabled={disabled}
      onChange={(e) => onChange(e.target.checked)}
      className="w-4 h-4 mt-0.5 accent-gold shrink-0"
    />
    <span className="flex flex-col">
      <span className="text-white/85 text-sm">{label}</span>
      <span className="text-white/40 text-xs">{hint}</span>
    </span>
  </label>
);

/** One faction: its fields, then (once it exists) the rank ladder and the entry conditions. */
const FactionEditor = ({ factionId, canEdit, canDelete, onClose, onCreated }: FactionEditorProps) => {
  const [detail, setDetail] = useState<FactionAdminDetail | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  /** FEAT-206: «Основное» (fields, ranks, conditions) / «Экономика»; FEAT-207: «Территория и враги». */
  const [section, setSection] = useState<Section>('main');

  const load = useCallback(async () => {
    if (factionId == null) return;
    setLoadError(null);
    try {
      const d = await adminGetFaction(factionId);
      setDetail(d);
      setForm(formFrom(d));
    } catch (e) {
      setLoadError(apiErrorMessage(e, 'Не удалось загрузить фракцию'));
    }
  }, [factionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }));

  const save = async () => {
    const name = form.name.trim();
    if (!name || name.length > FACTION_LIMITS.nameMax) {
      toast.error(`Название: от 1 до ${FACTION_LIMITS.nameMax} символов`);
      return;
    }
    if (form.description.length > FACTION_LIMITS.descriptionMax) {
      toast.error(`Описание: до ${FACTION_LIMITS.descriptionMax} символов`);
      return;
    }
    const limit = form.member_limit.trim() === '' ? null : toInt(form.member_limit);
    if (form.member_limit.trim() !== '' && (limit == null || limit < 1 || limit > FACTION_LIMITS.memberLimitMax)) {
      toast.error(`Лимит участников: от 1 до ${FACTION_LIMITS.memberLimitMax} или пусто`);
      return;
    }
    if (form.leader_npc_ids.length > FACTION_LIMITS.leadersMax) {
      toast.error(`Руководителей — не больше ${FACTION_LIMITS.leadersMax}`);
      return;
    }
    const body: FactionInput = {
      name,
      description: form.description.trim() || null,
      emblem_url: form.emblem_url,
      hq_location_id: form.hq_location_id,
      leader_npc_ids: form.leader_npc_ids.length ? form.leader_npc_ids : null,
      member_limit: limit,
      is_invite_only: form.is_invite_only,
      is_secret: form.is_secret,
      is_active: form.is_active,
      sort_order: toInt(form.sort_order) ?? 0,
    };
    setSaving(true);
    try {
      if (factionId == null) {
        const created = await adminCreateFaction(body);
        toast.success('Фракция создана — теперь добавьте звания и условия');
        onCreated(created.id);
      } else {
        const updated = await adminUpdateFaction(factionId, body);
        setDetail(updated);
        setForm(formFrom(updated));
        toast.success('Фракция сохранена');
      }
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить фракцию'));
    } finally {
      setSaving(false);
    }
  };

  const ro = !canEdit;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <button type="button" onClick={onClose} className="text-white/60 hover:text-white text-sm flex items-center gap-1 self-start">
          <ArrowLeft size={15} />К списку фракций
        </button>
        <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase tracking-[0.06em] break-words">
          {factionId == null ? 'Новая фракция' : detail?.name ?? 'Фракция'}
        </h2>
        {detail && <span className="text-white/40 text-xs sm:ml-auto">Участников: {detail.member_count}</span>}
      </div>

      {loadError && (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-site-red text-sm">{loadError}</p>
          <button type="button" className="btn-line !w-auto !text-xs !py-1 !px-3" onClick={() => void load()}>
            Повторить
          </button>
        </div>
      )}

      {detail && (
        <SubTabs<Section>
          tabs={[
            { key: 'main', label: 'Основное' },
            { key: 'territory', label: 'Территория и враги' },
            { key: 'economy', label: 'Экономика' },
          ]}
          active={section}
          onChange={setSection}
        />
      )}

      {detail && section === 'territory' && (
        <>
          <TerritoryTab
            factionId={detail.id}
            factionName={detail.name}
            isSecret={detail.is_secret}
            isActive={detail.is_active}
            ranks={detail.ranks}
            canEdit={canEdit}
          />
          <EnemiesEditor factionId={detail.id} canEdit={canEdit} />
          <OutlawRegionsEditor factionId={detail.id} isSecret={detail.is_secret} canEdit={canEdit} />
        </>
      )}

      {detail && section === 'economy' && (
        <FactionEconomyPanel factionId={detail.id} isSecret={detail.is_secret} ranks={detail.ranks} />
      )}

      {(factionId == null || detail) && section === 'main' && (
        <section className="gray-bg p-4 sm:p-6 flex flex-col gap-5">
          <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Основное</h3>
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-5">
            <div className="flex flex-col gap-4 min-w-0">
              <label className="flex flex-col gap-1">
                <span className={LABEL}>Название</span>
                <input
                  value={form.name}
                  maxLength={FACTION_LIMITS.nameMax}
                  disabled={ro}
                  onChange={(e) => set('name', e.target.value)}
                  className={FIELD}
                  placeholder="Орден Зари"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className={LABEL}>Описание</span>
                <textarea
                  value={form.description}
                  maxLength={FACTION_LIMITS.descriptionMax}
                  disabled={ro}
                  onChange={(e) => set('description', e.target.value)}
                  rows={5}
                  className="textarea-bordered text-sm"
                  placeholder="История, цели, кого принимают..."
                />
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="flex flex-col gap-1 min-w-0">
                  <span className={LABEL}>Штаб (локация)</span>
                  {ro ? (
                    <span className="text-white/80 text-sm">{detail?.hq_location_name ?? '—'}</span>
                  ) : (
                    <EntityPicker kind="location" value={form.hq_location_id} onChange={(id) => set('hq_location_id', id)} />
                  )}
                </div>
                <div className="flex flex-col gap-1 min-w-0">
                  <span className={LABEL}>Руководители (НПС, до {FACTION_LIMITS.leadersMax})</span>
                  {ro ? (
                    <span className="text-white/80 text-sm">{detail?.leaders.map((l) => l.name).join(', ') || '—'}</span>
                  ) : (
                    <EntityListPicker
                      kind="npc"
                      ids={form.leader_npc_ids}
                      onChange={(ids) => set('leader_npc_ids', ids.slice(0, FACTION_LIMITS.leadersMax))}
                    />
                  )}
                </div>
                <label className="flex flex-col gap-1">
                  <span className={LABEL}>Лимит участников</span>
                  <input
                    inputMode="numeric"
                    value={form.member_limit}
                    disabled={ro}
                    onChange={(e) => INT_RE.test(e.target.value) && set('member_limit', e.target.value)}
                    className={FIELD}
                    placeholder="без лимита"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={LABEL}>Порядок в каталоге</span>
                  <input
                    inputMode="numeric"
                    value={form.sort_order}
                    disabled={ro}
                    onChange={(e) => SIGNED_INT_RE.test(e.target.value) && set('sort_order', e.target.value)}
                    className={FIELD}
                  />
                </label>
              </div>
              <div className="flex flex-col gap-3">
                <Toggle
                  checked={form.is_active}
                  disabled={ro}
                  onChange={(v) => set('is_active', v)}
                  label="Показывать в каталоге"
                  hint="Выключено — черновик: фракции нет в каталоге, вступить нельзя; участники остаются"
                />
                <Toggle
                  checked={form.is_invite_only}
                  disabled={ro}
                  onChange={(v) => set('is_invite_only', v)}
                  label="Только по заявке"
                  hint="Игрок подаёт заявку, её одобряют во вкладке «Заявки»"
                />
                <Toggle
                  checked={form.is_secret}
                  disabled={ro}
                  onChange={(v) => set('is_secret', v)}
                  label="Тайная"
                  hint="Членство видно только самому игроку и администрации; в каталоге нет числа участников"
                />
              </div>
            </div>
            <div className="min-w-0">
              {ro ? (
                form.emblem_url ? <img src={form.emblem_url} alt="" className="w-full rounded-card" /> : null
              ) : (
                <ImageField label="Герб" value={form.emblem_url} onChange={(url) => set('emblem_url', url)} />
              )}
            </div>
          </div>
          {canEdit && (
            <div className="flex flex-col sm:flex-row gap-3">
              <button type="button" onClick={() => void save()} disabled={saving} className="btn-blue !text-base !px-8 !py-2 disabled:opacity-50">
                {saving ? 'Сохранение...' : factionId == null ? 'Создать' : 'Сохранить'}
              </button>
            </div>
          )}
        </section>
      )}

      {detail && section === 'main' && (
        <>
          <RanksEditor factionId={detail.id} ranks={detail.ranks} canEdit={canEdit} canDelete={canDelete} onChanged={() => void load()} />
          <ConditionsEditor
            factionId={detail.id}
            conditions={detail.conditions}
            canEdit={canEdit}
            onSaved={() => void load()}
          />
          {detail.hostilities.length > 0 && (
            <section className="gray-bg p-4 sm:p-6 flex flex-col gap-2">
              <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Враждебность</h3>
              {detail.hostilities.map((h) => (
                <p key={h.id} className="text-white/75 text-sm">
                  {h.faction_a_id === detail.id ? h.faction_b_name : h.faction_a_name}
                  {h.irreconcilable ? <span className="text-site-red"> · непримиримая</span> : null}
                </p>
              ))}
              <p className="text-white/40 text-xs">Пары правятся во вкладке «Враждебность».</p>
            </section>
          )}
        </>
      )}
    </div>
  );
};

export default FactionEditor;
