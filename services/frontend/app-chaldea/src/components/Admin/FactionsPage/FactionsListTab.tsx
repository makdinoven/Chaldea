import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { EyeOff, Flag, Plus } from 'lucide-react';
import { adminDeleteFaction, adminListFactions, type FactionAdminListItem } from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import FactionEditor from './FactionEditor';

interface FactionsListTabProps {
  canEdit: boolean;
  canDelete: boolean;
}

type EditorTarget = { id: number | null } | null;

const Chip = ({ children, tone = 'muted' }: { children: string; tone?: 'muted' | 'gold' | 'red' }) => (
  <span
    className={`px-2 py-0.5 rounded-full text-[10px] font-medium uppercase whitespace-nowrap ${
      tone === 'gold' ? 'bg-gold/15 text-gold' : tone === 'red' ? 'bg-site-red/15 text-site-red' : 'bg-white/10 text-white/60'
    }`}
  >
    {children}
  </span>
);

const FactionsListTab = ({ canEdit, canDelete }: FactionsListTabProps) => {
  const [list, setList] = useState<FactionAdminListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editor, setEditor] = useState<EditorTarget>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setList(await adminListFactions());
    } catch (e) {
      setError(apiErrorMessage(e, 'Не удалось загрузить фракции'));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const remove = async (f: FactionAdminListItem) => {
    if (!window.confirm(`Удалить фракцию «${f.name}»? Удалить можно только фракцию, в которой никогда не было участников.`)) return;
    try {
      await adminDeleteFaction(f.id);
      toast.success('Фракция удалена');
      void load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось удалить фракцию'));
    }
  };

  if (editor) {
    return (
      <FactionEditor
        factionId={editor.id}
        canEdit={canEdit}
        canDelete={canDelete}
        onClose={() => {
          setEditor(null);
          void load();
        }}
        onCreated={(id) => setEditor({ id })}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {canEdit && (
        <button type="button" className="btn-blue !w-full sm:!w-auto !text-sm !px-5 !py-2 self-start inline-flex items-center gap-1.5" onClick={() => setEditor({ id: null })}>
          <Plus size={15} />
          Создать фракцию
        </button>
      )}

      {error && <p className="text-site-red text-sm">{error}</p>}
      {!list && !error && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
      {list?.length === 0 && <p className="text-white/50 text-sm">Фракций пока нет.</p>}

      <div className="flex flex-col gap-2">
        {list?.map((f) => (
          <div key={f.id} className="flex flex-col sm:flex-row sm:items-center gap-3 bg-white/[0.03] border border-white/[0.06] rounded-card p-3 sm:p-4">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <div className="w-11 h-11 shrink-0 rounded-[10px] bg-black/30 border border-white/10 overflow-hidden flex items-center justify-center">
                {f.emblem_url ? <img src={f.emblem_url} alt="" className="w-full h-full object-cover" /> : <Flag size={20} className="text-white/30" />}
              </div>
              <div className="min-w-0 flex flex-col gap-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-white text-sm font-medium break-words">{f.name}</span>
                  {f.is_active ? <Chip tone="gold">в каталоге</Chip> : <Chip>черновик</Chip>}
                  {f.is_invite_only && <Chip>по заявке</Chip>}
                  {f.is_secret && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/10 text-white/60 text-[10px] uppercase">
                      <EyeOff size={10} />
                      тайная
                    </span>
                  )}
                  {f.pending_applications > 0 && <Chip tone="red">{`заявок: ${f.pending_applications}`}</Chip>}
                </div>
                <span className="text-white/40 text-xs">
                  ID {f.id} · участников {f.member_count}
                  {f.member_limit != null ? ` / ${f.member_limit}` : ''} · званий {f.rank_count} · условий {f.condition_count} · порядок {f.sort_order}
                </span>
              </div>
            </div>
            <div className="flex gap-4 shrink-0">
              <button type="button" onClick={() => setEditor({ id: f.id })} className="text-sm text-white hover:text-site-blue transition-colors">
                {canEdit ? 'Редактировать' : 'Открыть'}
              </button>
              {canDelete && (
                <button type="button" onClick={() => void remove(f)} className="text-sm text-site-red hover:text-white transition-colors">
                  Удалить
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default FactionsListTab;
