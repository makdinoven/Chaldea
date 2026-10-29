import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ArrowLeft } from 'lucide-react';
import { fetchEconomySummary } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { useAppSelector } from '../../../redux/store';
import { selectPermissions } from '../../../redux/slices/userSlice';
import { hasPermission } from '../../../utils/permissions';
import type { EconSummary } from '../../../types/economy';
import EconomySummary from './EconomySummary';
import EconomyJournal from './EconomyJournal';
import EconomyActions from './EconomyActions';
import EconomySettings from './EconomySettings';
import EconomyRegions from './EconomyRegions';
import EconomyGoodsGroups from './EconomyGoodsGroups';
import EconomyItemGroups from './EconomyItemGroups';
import EconomyTemplates from './EconomyTemplates';
import EconomyTick from './EconomyTick';
import EconomyMerchants from './EconomyMerchants';

type EconomyTab =
  | 'summary'
  | 'journal'
  | 'actions'
  | 'regions'
  | 'goods'
  | 'items'
  | 'templates'
  | 'merchants'
  | 'tick'
  | 'settings';

const TAB_LABEL: Record<EconomyTab, string> = {
  summary: 'Сводка',
  journal: 'Журнал',
  actions: 'Действия',
  regions: 'Регионы',
  goods: 'Товары',
  items: 'Предметы',
  templates: 'Шаблоны',
  merchants: 'Торговцы',
  tick: 'Пересчёт',
  settings: 'Настройки',
};

/** Admin «Экономика» (FEAT-181): where the world's money is, the ledger journal, admin postings, currency settings. */
const EconomyPage = () => {
  const permissions = useAppSelector(selectPermissions);
  const canEmit = hasPermission(permissions, 'economy:emit');
  const canAdjust = hasPermission(permissions, 'economy:adjust');
  const canSettings = hasPermission(permissions, 'economy:settings');

  const [tab, setTab] = useState<EconomyTab>('summary');
  const [summary, setSummary] = useState<EconSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadSummary = useCallback(() => {
    setRefreshing(true);
    fetchEconomySummary()
      .then((s) => {
        setSummary(s);
        setSummaryError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить сводку экономики');
        setSummaryError(msg);
        toast.error(msg);
      })
      .finally(() => setRefreshing(false));
  }, []);

  useEffect(loadSummary, [loadSummary]);

  const tabs: EconomyTab[] = [
    'summary',
    'journal',
    ...(canEmit || canAdjust ? (['actions'] as EconomyTab[]) : []),
    'regions',
    'goods',
    'items',
    'templates',
    'merchants',
    'tick',
    'settings',
  ];

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-5 pb-10">
      <Link to="/admin" className="self-start text-white/60 hover:text-white text-sm flex items-center gap-1">
        <ArrowLeft size={15} />
        Админ-панель
      </Link>
      <div className="flex flex-col gap-1.5">
        <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">Экономика</h1>
        <p className="text-white/60 text-sm max-w-2xl">
          Все деньги мира лежат на счетах: у персонажей, в казнах регионов и стран, в Казне Скитальцев или
          на аукционе, а у жителей регионов — в общем кошельке. Деньги только переходят со счёта на счёт; новые
          появляются лишь эмиссией.
        </p>
      </div>

      <div className="flex gap-1 sm:gap-2 border-b border-white/10 overflow-x-auto gold-scrollbar">
        {tabs.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-3 sm:px-4 py-2 -mb-px border-b-2 text-sm uppercase tracking-[0.06em] whitespace-nowrap transition-colors duration-200 ease-site ${
              t === tab ? 'border-gold text-gold' : 'border-transparent text-white/50 hover:text-white'
            }`}
          >
            {TAB_LABEL[t]}
          </button>
        ))}
      </div>

      {tab === 'summary' && (
        <>
          {summaryError && !summary && <p className="text-site-red text-sm">{summaryError}</p>}
          {!summary && !summaryError && (
            <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
          )}
          {summary && <EconomySummary summary={summary} refreshing={refreshing} onRefresh={loadSummary} />}
        </>
      )}
      {tab === 'journal' && <EconomyJournal summary={summary} />}
      {tab === 'actions' && <EconomyActions canEmit={canEmit} canAdjust={canAdjust} onDone={loadSummary} />}
      {tab === 'regions' && <EconomyRegions canSettings={canSettings} canEmit={canEmit} onMoneyChanged={loadSummary} />}
      {tab === 'goods' && <EconomyGoodsGroups />}
      {tab === 'items' && <EconomyItemGroups />}
      {tab === 'templates' && <EconomyTemplates />}
      {tab === 'merchants' && (
        <EconomyMerchants canSettings={canSettings} canEmit={canEmit} onMoneyChanged={loadSummary} />
      )}
      {tab === 'tick' && <EconomyTick canSettings={canSettings} onMoneyChanged={loadSummary} />}
      {tab === 'settings' && <EconomySettings canEdit={canSettings} onSaved={loadSummary} />}
    </div>
  );
};

export default EconomyPage;
