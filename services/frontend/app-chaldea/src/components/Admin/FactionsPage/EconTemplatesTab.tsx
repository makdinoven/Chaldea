// FEAT-206 — «Шаблоны экономики» of factions: profile of incomes / expenses and the starting numbers.
// Reading needs factions:read; create / edit / delete — factions:economy. A used template cannot be deleted.
import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Pencil, Trash2 } from 'lucide-react';
import {
  FACTION_ECON_PARAM_SPECS,
  FACTION_PROFILE_KINDS,
  FACTION_PROFILE_KIND_LABEL,
  adminCreateEconTemplate,
  adminDeleteEconTemplate,
  adminListEconTemplates,
  adminUpdateEconTemplate,
  type FactionEconParams,
  type FactionEconTemplate,
} from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import ConfirmDialog from '../../pages/LocationPage/ConfirmDialog';
import { FIELD, INT_RE, LABEL, OPTION, SIGNED_INT_RE, toInt } from './adminShared';

const CODE_RE = /^[a-z0-9_]{2,32}$/;
const DEC_RE = /^\d*([.,]\d{0,6})?$/;
const NAME_MAX = 100;
const DESCRIPTION_MAX = 500;

interface TemplateForm {
  code: string;
  name: string;
  description: string;
  sort_order: string;
  params: Record<string, string>;
}

const formOf = (t: FactionEconTemplate | null): TemplateForm => ({
  code: t?.code ?? '',
  name: t?.name ?? '',
  description: t?.description ?? '',
  sort_order: String(t?.sort_order ?? 0),
  params: Object.fromEntries(FACTION_ECON_PARAM_SPECS.map((s) => [s.key, t ? String(t.params[s.key] ?? '') : s.kind === 'kind' ? 'none' : ''])),
});

const paramsBody = (raw: Record<string, string>): FactionEconParams | null => {
  const out: FactionEconParams = {};
  for (const spec of FACTION_ECON_PARAM_SPECS) {
    const v = (raw[spec.key] ?? '').trim();
    if (!v) continue;
    if (spec.kind === 'kind') {
      out[spec.key] = v;
      continue;
    }
    const n = Number(v.replace(',', '.'));
    if (!Number.isFinite(n) || (spec.kind === 'int' && !Number.isInteger(n)) || n < (spec.min ?? 0) || n > (spec.max ?? Infinity)) {
      toast.error(`${spec.label}: ${spec.kind === 'int' ? 'целое число ' : ''}от ${spec.min} до ${spec.max}`);
      return null;
    }
    out[spec.key] = spec.kind === 'int' ? n : v.replace(',', '.');
  }
  return out;
};

const TemplateModal = ({
  template,
  onClose,
  onSaved,
}: {
  /** null → a new template */
  template: FactionEconTemplate | null;
  onClose: () => void;
  onSaved: () => void;
}) => {
  const [form, setForm] = useState<TemplateForm>(() => formOf(template));
  const [saving, setSaving] = useState(false);
  const set = <K extends keyof TemplateForm>(k: K, v: TemplateForm[K]) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    const name = form.name.trim();
    if (!template && !CODE_RE.test(form.code.trim())) {
      toast.error('Код шаблона: от 2 до 32 символов — латиница в нижнем регистре, цифры и «_»');
      return;
    }
    if (!name || name.length > NAME_MAX) return void toast.error(`Название: от 1 до ${NAME_MAX} символов`);
    if (form.description.length > DESCRIPTION_MAX) return void toast.error(`Описание: до ${DESCRIPTION_MAX} символов`);
    const params = paramsBody(form.params);
    if (!params) return;
    const body = {
      name,
      description: form.description.trim() || null,
      params,
      sort_order: toInt(form.sort_order) ?? 0,
    };
    setSaving(true);
    try {
      if (template) await adminUpdateEconTemplate(template.code, body);
      else await adminCreateEconTemplate({ ...body, code: form.code.trim() });
      toast.success(template ? 'Шаблон сохранён' : 'Шаблон создан');
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить шаблон'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalShell
      open
      onClose={onClose}
      title={template ? `Шаблон «${template.name}»` : 'Новый шаблон экономики'}
      size="lg"
      dismissible={!saving}
      closeOnBackdrop={false}
      footer={
        <>
          <button type="button" className="btn-line w-full sm:w-auto" onClick={onClose} disabled={saving}>
            Отмена
          </button>
          <button type="button" className="btn-blue w-full sm:w-auto disabled:opacity-50" onClick={() => void save()} disabled={saving}>
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <label className="flex flex-col gap-1 min-w-0">
            <span className={LABEL}>Код</span>
            <input
              value={form.code}
              disabled={!!template}
              maxLength={32}
              onChange={(e) => set('code', e.target.value.toLowerCase())}
              className={FIELD}
              placeholder="order"
            />
          </label>
          <label className="flex flex-col gap-1 min-w-0">
            <span className={LABEL}>Название</span>
            <input value={form.name} maxLength={NAME_MAX} onChange={(e) => set('name', e.target.value)} className={FIELD} placeholder="Орден" />
          </label>
          <label className="flex flex-col gap-1 min-w-0">
            <span className={LABEL}>Порядок</span>
            <input inputMode="numeric" value={form.sort_order} onChange={(e) => SIGNED_INT_RE.test(e.target.value) && set('sort_order', e.target.value)} className={FIELD} />
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={LABEL}>Описание</span>
          <textarea
            value={form.description}
            maxLength={DESCRIPTION_MAX}
            onChange={(e) => set('description', e.target.value)}
            rows={2}
            className="textarea-bordered text-sm"
          />
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {FACTION_ECON_PARAM_SPECS.map((spec) => (
            <label key={spec.key} className="flex flex-col gap-1 min-w-0">
              <span className="text-white/70 text-xs">{spec.label}</span>
              {spec.kind === 'kind' ? (
                <select
                  value={form.params[spec.key] || 'none'}
                  onChange={(e) => set('params', { ...form.params, [spec.key]: e.target.value })}
                  className={FIELD}
                >
                  {FACTION_PROFILE_KINDS.map((k) => (
                    <option key={k} value={k} className={OPTION}>
                      {FACTION_PROFILE_KIND_LABEL[k]}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  inputMode="decimal"
                  value={form.params[spec.key] ?? ''}
                  onChange={(e) =>
                    (spec.kind === 'int' ? INT_RE : DEC_RE).test(e.target.value) &&
                    set('params', { ...form.params, [spec.key]: e.target.value })
                  }
                  className={FIELD}
                  placeholder="по умолчанию"
                />
              )}
              <span className="text-white/40 text-xs break-words">
                {spec.hint}
                {spec.kind !== 'kind' ? ` (${spec.min}…${spec.max})` : ''}
              </span>
            </label>
          ))}
        </div>
      </div>
    </ModalShell>
  );
};

const paramLine = (t: FactionEconTemplate): string => {
  const p = t.params;
  const kind = FACTION_PROFILE_KIND_LABEL[p.profile_kind as keyof typeof FACTION_PROFILE_KIND_LABEL] ?? String(p.profile_kind);
  return `участников ${p.start_members} · норма ${p.norm_per_member}/уч. · старт ${p.start_treasury_per_member}/уч. · взнос ${p.dues_per_member} · жалованье ${p.wage_per_member} · профиль: ${kind} · закупки ${p.qm_budget_share}`;
};

const EconTemplatesTab = ({ canEdit }: { canEdit: boolean }) => {
  const [list, setList] = useState<FactionEconTemplate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<FactionEconTemplate | 'new' | null>(null);
  const [deleting, setDeleting] = useState<FactionEconTemplate | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setList(await adminListEconTemplates());
    } catch (e) {
      setError(apiErrorMessage(e, 'Не удалось загрузить шаблоны экономики'));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const remove = async () => {
    if (!deleting) return;
    const t = deleting;
    setDeleting(null);
    try {
      await adminDeleteEconTemplate(t.code);
      toast.success('Шаблон удалён');
      void load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось удалить шаблон'));
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <p className="text-white/60 text-sm flex-1">
          Шаблон задаёт, откуда фракция берёт доход и сколько платит участникам. Фракции назначают шаблон во вкладке
          «Экономика» и могут переопределить любые числа.
        </p>
        {canEdit && (
          <button type="button" className="btn-blue !w-full sm:!w-auto !text-sm !px-6 shrink-0" onClick={() => setEditing('new')}>
            + Новый шаблон
          </button>
        )}
      </div>
      {error && (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-site-red text-sm">{error}</p>
          <button type="button" className="btn-line !w-auto !text-xs !py-1 !px-3" onClick={() => void load()}>
            Повторить
          </button>
        </div>
      )}
      {!list && !error && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
      {list && list.length === 0 && <p className="text-white/50 text-sm">Шаблонов нет.</p>}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {list?.map((t) => (
          <div key={t.code} className="gray-bg p-4 flex flex-col gap-2 min-w-0">
            <div className="flex items-start gap-2 min-w-0">
              <div className="flex-1 min-w-0">
                <p className="gold-text text-base font-medium break-words">{t.name}</p>
                <p className="text-white/40 text-xs">
                  {t.code} · используют фракций: {t.used_by}
                </p>
              </div>
              {canEdit && (
                <div className="flex gap-1 shrink-0">
                  <button type="button" className="p-1.5 text-white/60 hover:text-site-blue transition-colors" onClick={() => setEditing(t)} aria-label="Изменить">
                    <Pencil size={16} />
                  </button>
                  <button
                    type="button"
                    className="p-1.5 text-site-red hover:text-white transition-colors disabled:opacity-30"
                    onClick={() => setDeleting(t)}
                    disabled={t.used_by > 0}
                    title={t.used_by > 0 ? 'Шаблон используется' : 'Удалить'}
                    aria-label="Удалить"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              )}
            </div>
            {t.description && <p className="text-white/70 text-sm break-words">{t.description}</p>}
            <p className="text-white/50 text-xs break-words">{paramLine(t)}</p>
          </div>
        ))}
      </div>

      {editing && (
        <TemplateModal
          template={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void load();
          }}
        />
      )}
      {deleting && (
        <ConfirmDialog
          title="Удалить шаблон"
          message={`Удалить шаблон «${deleting.name}»?`}
          confirmLabel="Удалить"
          danger
          onConfirm={() => void remove()}
          onCancel={() => setDeleting(null)}
        />
      )}
    </div>
  );
};

export default EconTemplatesTab;
