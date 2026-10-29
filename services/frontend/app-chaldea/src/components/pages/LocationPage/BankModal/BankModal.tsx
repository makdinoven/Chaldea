import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { useDispatch } from 'react-redux';
import goldCoinsIcon from '../../../../assets/icons/gold-coins.svg';
import { getBankView } from '../../../../api/bank';
import { fetchProfile } from '../../../../redux/slices/profileSlice';
import type { AppDispatch } from '../../../../redux/store';
import { useAppSelector } from '../../../../redux/store';
import type { BankView } from '../../../../types/bank';
import ModalShell from '../../../CommonComponents/ModalShell/ModalShell';
import BankDepositsTab from './BankDepositsTab';
import BankLoanTab from './BankLoanTab';
import BankTransfersTab from './BankTransfersTab';
import { bankErrorText, newRequestId, regionLabel } from './bankFormat';
import { DebtorBadge, type BankRun } from './BankParts';

interface BankModalProps {
  npcId: number;
  npcName: string;
  npcAvatar: string | null;
  onClose: () => void;
}

type BankTab = 'deposits' | 'loan' | 'transfers';

const TABS: { key: BankTab; label: string }[] = [
  { key: 'deposits', label: 'Вклады' },
  { key: 'loan', label: 'Займ' },
  { key: 'transfers', label: 'Переводы' },
];

/** FEAT-184 — the regional bank at a banker NPC (deposits, loan, transfers). */
const BankModal = ({ npcId, npcName, npcAvatar, onClose }: BankModalProps) => {
  const dispatch = useDispatch<AppDispatch>();
  const characterId = useAppSelector((s) => s.user.character?.id ?? null) as number | null;

  const [tab, setTab] = useState<BankTab>('deposits');
  const [view, setView] = useState<BankView | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  /** Guards double submits between the click and the re-render that disables the buttons. */
  const pendingRef = useRef(false);

  const load = useCallback(async () => {
    if (!characterId) {
      setLoading(false);
      setLoadError('Нужен персонаж, чтобы пользоваться банком');
      return;
    }
    setLoading(true);
    try {
      setView(await getBankView(npcId, characterId));
      setLoadError(null);
    } catch (err) {
      const text = bankErrorText(err, 'Не удалось открыть банк');
      setLoadError(text);
      toast.error(text);
    } finally {
      setLoading(false);
    }
  }, [npcId, characterId]);

  useEffect(() => {
    void load();
  }, [load]);

  const run: BankRun = async (call, fallback) => {
    if (pendingRef.current || !characterId) return false;
    pendingRef.current = true;
    setPending(true);
    try {
      const res = await call(newRequestId());
      setView(res.view);
      toast.success(res.message);
      // The header balance follows the profile (userSlice matcher on fetchProfile).
      dispatch(fetchProfile(characterId));
      return true;
    } catch (err) {
      toast.error(bankErrorText(err, fallback));
      // Balances or the bank may have moved under us: show the fresh state.
      void load();
      return false;
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  };

  const icon = (
    <div className="gold-outline relative w-9 h-9 rounded-full overflow-hidden bg-black/40 shrink-0">
      {npcAvatar ? (
        <img src={npcAvatar} alt={npcName} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-lg" aria-hidden>
          🏦
        </div>
      )}
    </div>
  );

  return (
    <ModalShell open onClose={onClose} title={npcName} size="lg" icon={icon} dismissible={!pending}>
      {loading && !view ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      ) : !view ? (
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <p className="text-site-red text-sm">{loadError ?? 'Не удалось открыть банк'}</p>
          {characterId && (
            <button type="button" className="btn-line" onClick={() => void load()}>
              Повторить
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4 min-w-0">
          {/* Bank, debtor mark, wallet */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex flex-col min-w-0">
              <span className="text-white/50 text-xs uppercase tracking-wide">Банк региона</span>
              <span className="text-white text-sm sm:text-base font-medium truncate">
                {view.region_id ? `«${regionLabel(view.region_name)}»` : '—'}
              </span>
            </div>
            {view.debtor && <DebtorBadge />}
            <div
              className="ml-auto flex items-center gap-1.5 bg-black/30 rounded-card px-3 py-1.5 shrink-0"
              title="В кошельке"
            >
              <img src={goldCoinsIcon} alt="" className="w-5 h-5" />
              <span className="text-gold font-medium text-sm sm:text-base">{view.wallet.toLocaleString('ru-RU')}</span>
            </div>
          </div>

          {!view.bank_enabled && (
            <div className="rounded-card border border-white/15 bg-white/[0.03] px-3 py-2 text-xs sm:text-sm text-white/70">
              <span className="text-gold font-medium">Банк закрыт.</span> Новые вклады и займы не принимаются,
              проценты по вкладам не начисляются. Снять вклад этого банка, перевести вклад и погасить займ — можно.
            </div>
          )}

          {/* Tabs (scroll horizontally on narrow screens) */}
          <div className="flex border-b border-white/10 overflow-x-auto">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => setTab(t.key)}
                className={`flex-1 min-w-[96px] pb-2 text-sm sm:text-base font-medium uppercase tracking-wide whitespace-nowrap transition-colors duration-200 border-b-2 ${
                  tab === t.key ? 'text-gold border-gold' : 'text-white/50 border-transparent hover:text-white/80'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {characterId && tab === 'deposits' && (
            <BankDepositsTab view={view} characterId={characterId} npcId={npcId} pending={pending} run={run} />
          )}
          {characterId && tab === 'loan' && (
            <BankLoanTab view={view} characterId={characterId} npcId={npcId} pending={pending} run={run} />
          )}
          {characterId && tab === 'transfers' && (
            <BankTransfersTab view={view} characterId={characterId} npcId={npcId} pending={pending} run={run} />
          )}
        </div>
      )}
    </ModalShell>
  );
};

export default BankModal;
