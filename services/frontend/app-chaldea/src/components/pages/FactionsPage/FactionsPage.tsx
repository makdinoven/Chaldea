import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Flag, Send } from 'lucide-react';
import {
  applyToFaction,
  cancelFactionApplication,
  fetchFactionCatalog,
  joinFaction,
  type FactionCatalogItem,
} from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import { useAppSelector } from '../../../redux/store';
import { useSubclassNames } from '../../../utils/factionText';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import FactionCard from './FactionCard';

const MESSAGE_MAX = 500;

/**
 * FEAT-205 — «Фракции»: the catalog of lore factions (orders, guilds, temples). Conditions are
 * evaluated for the active character (✓/✗); join, or apply with an optional message for the
 * invite-only ones. Secret factions are listed without member counts.
 */
const FactionsPage = () => {
  const character = useAppSelector((state) => state.user.character);
  const characterId = character?.id ?? null;
  const [factions, setFactions] = useState<FactionCatalogItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [applying, setApplying] = useState<FactionCatalogItem | null>(null);
  const [message, setMessage] = useState('');
  const subclassNames = useSubclassNames((m) => toast.error(m));

  const load = useCallback(async () => {
    setError(null);
    try {
      setFactions(await fetchFactionCatalog(characterId));
    } catch (err) {
      setError(apiErrorMessage(err, 'Не удалось загрузить фракции'));
    }
  }, [characterId]);

  useEffect(() => {
    void load();
  }, [load]);

  const join = async (faction: FactionCatalogItem) => {
    if (!characterId) return;
    setBusy(true);
    try {
      const res = await joinFaction(characterId, faction.id);
      const extra = res.notices_text.length > 0 ? res.notices_text.join('\n') : null;
      toast.success(extra ?? `Вы вступили во фракцию «${faction.name}»`, { duration: 6000 });
      await load();
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Не удалось вступить во фракцию'));
      void load();
    } finally {
      setBusy(false);
    }
  };

  const submitApplication = async () => {
    if (!characterId || !applying) return;
    setBusy(true);
    try {
      await applyToFaction(characterId, applying.id, message.trim() || null);
      toast.success('Заявка подана. Её рассмотрит администрация.');
      setApplying(null);
      setMessage('');
      await load();
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Не удалось подать заявку'));
    } finally {
      setBusy(false);
    }
  };

  const cancelApplication = async (faction: FactionCatalogItem) => {
    const applicationId = faction.my?.application_id;
    if (!characterId || !applicationId) return;
    setBusy(true);
    try {
      await cancelFactionApplication(characterId, applicationId);
      toast.success('Заявка отозвана');
      await load();
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Не удалось отозвать заявку'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-5 pb-10">
      <div className="flex flex-col gap-1.5">
        <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">Фракции</h1>
        <p className="text-white/60 text-sm max-w-3xl">
          Ордена, гильдии, храмы и тайные общества мира. Состоять можно в нескольких сразу, если они не враждуют
          непримиримо. Внутри фракции копятся очки за её задания, а звания приходят сами, как только выполнены их
          условия.
        </p>
        {!characterId && (
          <p className="text-gold-light text-sm">Выберите активного персонажа, чтобы видеть свои условия и вступать.</p>
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
      {!factions && !error && (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      )}
      {factions?.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-16 text-center">
          <Flag size={36} strokeWidth={1.5} className="text-white/20" />
          <p className="text-white/50 text-sm">Фракций пока нет.</p>
        </div>
      )}

      {factions && factions.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-5 items-start">
          {factions.map((f) => (
            <FactionCard
              key={f.id}
              faction={f}
              hasCharacter={characterId !== null}
              busy={busy}
              subclassNames={subclassNames}
              onJoin={(x) => void join(x)}
              onApply={(x) => {
                setMessage('');
                setApplying(x);
              }}
              onCancelApplication={(x) => void cancelApplication(x)}
            />
          ))}
        </div>
      )}

      <ModalShell
        open={applying !== null}
        onClose={() => setApplying(null)}
        title="Заявка во фракцию"
        icon={<Send size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
        size="sm"
        dismissible={!busy}
        footer={
          <>
            <button type="button" className="btn-line w-full sm:w-auto" onClick={() => setApplying(null)} disabled={busy}>
              Отмена
            </button>
            <button
              type="button"
              className="btn-blue w-full sm:w-auto disabled:opacity-50"
              onClick={() => void submitApplication()}
              disabled={busy}
            >
              {busy ? 'Отправка...' : 'Подать заявку'}
            </button>
          </>
        }
      >
        {applying && (
          <div className="flex flex-col gap-3">
            <p className="text-white/85 text-sm">
              Заявка во фракцию <span className="text-gold">«{applying.name}»</span>. Её рассмотрит администрация; при
              одобрении условия проверят ещё раз.
            </p>
            <label className="flex flex-col gap-1.5">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Сообщение (необязательно)</span>
              <textarea
                value={message}
                maxLength={MESSAGE_MAX}
                onChange={(e) => setMessage(e.target.value)}
                rows={4}
                className="textarea-bordered text-sm"
                placeholder="Почему ваш персонаж хочет вступить..."
              />
              <span className="text-white/35 text-[11px] text-right font-mono tabular-nums">
                {message.length}/{MESSAGE_MAX}
              </span>
            </label>
          </div>
        )}
      </ModalShell>
    </div>
  );
};

export default FactionsPage;
