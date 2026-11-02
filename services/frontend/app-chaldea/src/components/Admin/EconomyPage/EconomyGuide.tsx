import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowDown,
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  Info,
  Loader2,
  RefreshCw,
  TriangleAlert,
  XCircle,
} from 'lucide-react';
import {
  fetchCaravanOverview,
  fetchEconomyBanks,
  fetchEconomyGoodsGroups,
  fetchEconomyItemGroups,
  fetchEconomyMerchants,
  fetchEconomyRegions,
  fetchEconomySettings,
  fetchEconomySim,
  fetchEconomyTemplates,
} from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { useCurrency } from '../../../hooks/useCurrency';
import type {
  CaravanOverview,
  EconBanksResponse,
  EconGoodsGroup,
  EconMerchantsResponse,
  EconRegionItem,
  EconRegionTemplate,
  EconSettings,
  EconSimState,
  EconSummary,
  EconTickRun,
} from '../../../types/economy';
import { formatDateTime, formatDecimal, formatPercent } from './economyLabels';
import { useBigMoney } from './CompactValue';
import { COMPACT_MONEY_FROM, compactNumber, exactNumber } from '../../../utils/compactNumber';
import {
  GUIDE_SECTION_TITLE,
  guideAnchorId,
  type EconomyTabId,
  type GuideSectionId,
} from './guideSections';

/* ------------------------------------------------------------------------------------------ data */

interface Loaded<T> {
  data: T | null;
  error: string | null;
}

const EMPTY: Loaded<never> = { data: null as never, error: null };

interface GuideData {
  settings: Loaded<EconSettings>;
  regions: Loaded<EconRegionItem[]>;
  templates: Loaded<EconRegionTemplate[]>;
  goods: Loaded<EconGoodsGroup[]>;
  items: Loaded<{ total: number; offMarket: number }>;
  merchants: Loaded<EconMerchantsResponse>;
  banks: Loaded<EconBanksResponse>;
  sim: Loaded<EconSimState>;
  caravans: Loaded<CaravanOverview>;
}

const settle = <T,>(r: PromiseSettledResult<T>, fallback: string): Loaded<T> =>
  r.status === 'fulfilled' ? { data: r.value, error: null } : { data: null, error: apiErrorMessage(r.reason, fallback) };

/** Templates whose regions «Заполнить регионы по шаблонам» opens a bank in (backend `BANK_TEMPLATE_CODES`). */
const BANK_TEMPLATES = ['capital', 'port'];

/* -------------------------------------------------------------------------------------- statuses */

type Tone = 'done' | 'warn' | 'bad' | 'info' | 'loading';

interface StepStatus {
  tone: Tone;
  lines: string[];
}

const TONE_ICON: Record<Tone, ReactNode> = {
  done: <CheckCircle2 size={18} className="text-stat-energy" />,
  warn: <TriangleAlert size={18} className="text-gold" />,
  bad: <XCircle size={18} className="text-site-red" />,
  info: <Info size={18} className="text-site-blue" />,
  loading: <Loader2 size={18} className="text-white/50 animate-spin" />,
};

const TONE_TEXT: Record<Tone, string> = {
  done: 'Готово',
  warn: 'Нужно внимание',
  bad: 'Проблема',
  info: 'Проверьте',
  loading: 'Загрузка…',
};

const loadingStatus: StepStatus = { tone: 'loading', lines: [] };
const errorStatus = (error: string): StepStatus => ({ tone: 'bad', lines: [`Не удалось загрузить данные: ${error}`] });

/** First error of several sources, or null. */
const firstError = (...sources: Loaded<unknown>[]): string | null => sources.find((s) => s.error)?.error ?? null;

const latestRun = (runs: EconTickRun[]): EconTickRun | null =>
  runs.reduce<EconTickRun | null>((best, r) => (best === null || r.id > best.id ? r : best), null);

const RUN_STATUS_TEXT: Record<string, string> = {
  running: 'идёт',
  done: 'готово',
  partial: 'с ошибками',
  failed: 'ошибка',
};

/* ------------------------------------------------------------------------------- small building blocks */

const Section = ({ id, children, className = '' }: { id: GuideSectionId; children: ReactNode; className?: string }) => (
  <section id={guideAnchorId(id)} className={`scroll-mt-24 flex flex-col gap-3 ${className}`}>
    {children}
  </section>
);

const H2 = ({ children }: { children: ReactNode }) => (
  <h2 className="gold-text text-xl sm:text-2xl font-semibold uppercase tracking-[0.06em]">{children}</h2>
);

const H3 = ({ children }: { children: ReactNode }) => (
  <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">{children}</h3>
);

const P = ({ children }: { children: ReactNode }) => <p className="text-white/80 text-sm leading-relaxed">{children}</p>;

const Note = ({ children }: { children: ReactNode }) => (
  <p className="text-white/70 text-sm leading-relaxed rounded-card border border-white/10 bg-white/[0.04] px-4 py-3">
    {children}
  </p>
);

const B = ({ children }: { children: ReactNode }) => <span className="text-white font-medium">{children}</span>;

const UL = ({ children }: { children: ReactNode }) => (
  <ul className="flex flex-col gap-1.5 text-white/80 text-sm leading-relaxed list-disc pl-5 marker:text-gold/60">
    {children}
  </ul>
);

const OL = ({ children }: { children: ReactNode }) => (
  <ol className="flex flex-col gap-1.5 text-white/80 text-sm leading-relaxed list-decimal pl-5 marker:text-gold/80">
    {children}
  </ol>
);

/* --------------------------------------------------------------------------------- money-flow diagram */

type NodeKind = 'source' | 'treasury' | 'people' | 'player' | 'business';

const NODE_CLASS: Record<NodeKind, string> = {
  source: 'border-gold/50 text-gold',
  treasury: 'border-site-blue/50 text-site-blue',
  people: 'border-stat-energy/50 text-stat-energy',
  player: 'border-white/30 text-white',
  business: 'border-rarity-epic/50 text-rarity-epic',
};

const Node = ({ kind, children }: { kind: NodeKind; children: ReactNode }) => (
  <span className={`inline-flex items-center rounded-card border px-2.5 py-1 text-xs sm:text-sm font-medium ${NODE_CLASS[kind]}`}>
    {children}
  </span>
);

interface Flow {
  from: [NodeKind, string];
  to: [NodeKind, string];
  what: string;
}

const FlowGroup = ({ title, flows }: { title: string; flows: Flow[] }) => (
  <div className="flex flex-col gap-2">
    <p className="text-white/50 text-xs uppercase tracking-[0.06em]">{title}</p>
    <ul className="flex flex-col gap-2">
      {flows.map((f) => (
        <li
          key={`${f.from[1]}-${f.to[1]}-${f.what}`}
          className="flex flex-col sm:flex-row sm:items-center gap-1.5 sm:gap-3 rounded-card bg-white/[0.03] px-3 py-2"
        >
          <span className="flex flex-wrap items-center gap-1.5 shrink-0">
            <Node kind={f.from[0]}>{f.from[1]}</Node>
            <ArrowRight size={16} className="text-white/40 shrink-0" />
            <Node kind={f.to[0]}>{f.to[1]}</Node>
          </span>
          <span className="text-white/70 text-xs sm:text-sm">{f.what}</span>
        </li>
      ))}
    </ul>
  </div>
);

const FLOWS_ADMIN: Flow[] = [
  { from: ['source', 'Эмиссия'], to: ['treasury', 'Казна региона / страны / Скитальцев'], what: 'вкладка «Действия» → «Эмиссия»' },
  { from: ['source', 'Эмиссия'], to: ['people', 'Кошелёк жителей'], what: '«Заполнить регионы по шаблонам» или «Эмиссия»' },
  { from: ['source', 'Эмиссия'], to: ['business', 'Касса торговца'], what: '«Пополнить кассы торговцев»' },
  { from: ['treasury', 'Казна региона'], to: ['business', 'Банк (свои деньги)'], what: 'стартовый капитал при открытии и «Капитал из казны»' },
];

const FLOWS_TICK: Flow[] = [
  { from: ['people', 'Кошелёк жителей'], to: ['treasury', 'Казна региона'], what: 'налог с дохода жителей' },
  { from: ['treasury', 'Казна региона'], to: ['treasury', 'Казна страны'], what: 'доля страны (по умолчанию 10 %) с каждого поступления в казну' },
  { from: ['treasury', 'Казна страны'], to: ['treasury', 'Казна региона'], what: 'грант: 25 % денег страны делится между её регионами — четверть по нехватке до нормы, остальное по числу жителей' },
  { from: ['treasury', 'Казна региона'], to: ['people', 'Кошелёк жителей'], what: 'жалованье' },
  { from: ['people', 'Кошелёк жителей'], to: ['business', 'Касса торговца'], what: 'жители покупают у живых торговцев' },
  { from: ['business', 'Касса торговца'], to: ['treasury', 'Казна региона'], what: 'налог с выручки торговца' },
  { from: ['business', 'Касса торговца'], to: ['people', 'Кошелёк жителей'], what: 'торговец докупает товар у региона и отдаёт излишек кассы' },
  { from: ['people', 'Кошелёк жителей'], to: ['business', 'Банк'], what: 'вклады жителей и погашение их займов (обратно — займы и проценты)' },
  { from: ['people', 'Кошелёк жителей (покупатель)'], to: ['business', 'Караваны в пути'], what: 'оплата каравана при отправке; за еду недостающее доплачивает казна региона-покупателя' },
  { from: ['business', 'Караваны в пути'], to: ['people', 'Кошелёк жителей (продавец)'], what: 'цена товара при доставке; пошлина между странами — в казну страны-покупателя' },
];

const FLOWS_PLAYERS: Flow[] = [
  { from: ['treasury', 'Казна региона'], to: ['player', 'Игрок'], what: 'награды за бои и задания в регионе, скупка у обычного торговца' },
  { from: ['player', 'Игрок'], to: ['treasury', 'Казна региона'], what: 'дома, участки, налог на дом, телепорт, покупки у обычного торговца' },
  { from: ['player', 'Игрок'], to: ['business', 'Касса торговца'], what: 'покупка у живого торговца (обратно — продажа ему)' },
  { from: ['player', 'Игрок'], to: ['business', 'Хранилище вкладов'], what: 'вклад в банк (обратно — снятие с процентами)' },
  { from: ['business', 'Банк'], to: ['player', 'Игрок'], what: 'займ (обратно — погашение)' },
  { from: ['treasury', 'Казна Скитальцев'], to: ['player', 'Игрок'], what: 'награды боевого пропуска и платежи вне регионов' },
];

/* -------------------------------------------------------------------------------------- the component */

interface EconomyGuideProps {
  summary: EconSummary | null;
  summaryError: string | null;
  /** Tabs this user can open (the «Действия» tab needs emit/adjust rights). */
  availableTabs: EconomyTabId[];
  canSettings: boolean;
  canEmit: boolean;
  /** Section to scroll to; `scrollNonce` changes on every request, so the same section can be re-opened. */
  section: GuideSectionId | null;
  scrollNonce: number;
  onOpenTab: (tab: EconomyTabId) => void;
  onOpenSection: (section: GuideSectionId) => void;
}

const TAB_NAME: Record<EconomyTabId, string> = {
  guide: 'Как настроить',
  summary: 'Сводка',
  journal: 'Журнал',
  actions: 'Действия',
  regions: 'Регионы',
  goods: 'Товары',
  items: 'Предметы',
  templates: 'Шаблоны',
  merchants: 'Торговцы',
  banks: 'Банки',
  events: 'События',
  mint: 'Монетный двор',
  caravans: 'Караваны',
  guild: 'Гильдия',
  tick: 'Пересчёт',
  settings: 'Настройки',
};

interface StepAction {
  label: string;
  tab?: EconomyTabId;
  /** Router path outside the economy page. */
  to?: string;
  section?: GuideSectionId;
}

interface Step {
  title: string;
  body: ReactNode;
  /** null — no existing endpoint gives this status; the step is shown without one. */
  status: StepStatus | null;
  actions: StepAction[];
}

/** «Как настроить» (FEAT-185): launch checklist, how the economy works, recipes. */
const EconomyGuide = ({
  summary,
  summaryError,
  availableTabs,
  canSettings,
  canEmit,
  section,
  scrollNonce,
  onOpenTab,
  onOpenSection,
}: EconomyGuideProps) => {
  const { format } = useCurrency();
  const { big } = useBigMoney();
  const [data, setData] = useState<GuideData>({
    settings: EMPTY,
    regions: EMPTY,
    templates: EMPTY,
    goods: EMPTY,
    items: EMPTY,
    merchants: EMPTY,
    banks: EMPTY,
    sim: EMPTY,
    caravans: EMPTY,
  });
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    Promise.allSettled([
      fetchEconomySettings(),
      fetchEconomyRegions(),
      fetchEconomyTemplates(),
      fetchEconomyGoodsGroups(),
      Promise.all([
        fetchEconomyItemGroups({ page: 1, page_size: 1 }),
        fetchEconomyItemGroups({ page: 1, page_size: 1, off_market: true }),
      ]).then(([all, off]) => ({ total: all.total, offMarket: off.total })),
      fetchEconomyMerchants(),
      fetchEconomyBanks(),
      fetchEconomySim(),
      fetchCaravanOverview(),
    ])
      .then(([settings, regions, templates, goods, items, merchants, banks, sim, caravans]) => {
        setData({
          settings: settle(settings, 'Не удалось загрузить настройки валюты'),
          regions: settle(regions, 'Не удалось загрузить регионы'),
          templates: settle(templates, 'Не удалось загрузить шаблоны'),
          goods: settle(goods, 'Не удалось загрузить группы товаров'),
          items: settle(items, 'Не удалось загрузить группы предметов'),
          merchants: settle(merchants, 'Не удалось загрузить торговцев'),
          banks: settle(banks, 'Не удалось загрузить банки'),
          sim: settle(sim, 'Не удалось загрузить пересчёт'),
          caravans: settle(caravans, 'Не удалось загрузить караваны'),
        });
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  useEffect(() => {
    if (!section) return;
    // Wait one frame so the tab content is in the DOM.
    const id = window.requestAnimationFrame(() => {
      document.getElementById(guideAnchorId(section))?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    return () => window.cancelAnimationFrame(id);
  }, [section, scrollNonce]);

  const loadErrors = [
    data.settings,
    data.regions,
    data.templates,
    data.goods,
    data.items,
    data.merchants,
    data.banks,
    data.sim,
    data.caravans,
  ].filter((s) => s.error).length;

  /* ---------------------------------------------------------------------------------- step statuses */

  const statusOf = (sources: Loaded<unknown>[], build: () => StepStatus): StepStatus => {
    if (loading) return loadingStatus;
    const err = firstError(...sources);
    return err ? errorStatus(err) : build();
  };

  const regions = data.regions.data ?? [];
  const templated = regions.filter((r) => r.template_code);
  const simulated = regions.filter((r) => r.simulated);

  const currencyStatus = statusOf([data.settings], () => {
    const s = data.settings.data as EconSettings;
    return {
      tone: 'info',
      lines: [
        `Валюта: «${s.currency.name}», сокращение «${s.currency.short}»`,
        `Доля страны с поступлений в казну региона: ${formatPercent(s.country_tax_rate)}`,
      ],
    };
  });

  const groupsStatus = statusOf([data.goods, data.items], () => {
    const goods = data.goods.data as EconGoodsGroup[];
    const items = data.items.data as { total: number; offMarket: number };
    return {
      tone: 'info',
      lines: [
        `Групп товаров: ${goods.length}`,
        `Предметов вне рынка (без группы, свитки, рецепты, легендарные и выше): ${items.offMarket} из ${items.total}`,
      ],
    };
  });

  const templatesStatus = statusOf([data.regions, data.templates], () => {
    const tpl = data.templates.data as EconRegionTemplate[];
    const noPeople = templated.filter((r) => r.population <= 0).length;
    const lines = [
      `Шаблонов: ${tpl.length}`,
      `Шаблон назначен: ${templated.length} из ${regions.length} регионов`,
      `В пересчёте (шаблон и жители): ${simulated.length}`,
    ];
    const people = simulated.reduce((s, r) => s + r.population, 0);
    if (people > 0) lines.push(`Жителей в пересчёте: ${compactNumber(people)} (точно ${exactNumber(people)})`);
    if (noPeople > 0) lines.push(`С шаблоном, но без жителей: ${noPeople} — они не участвуют в пересчёте`);
    return { tone: templated.length === 0 ? 'warn' : noPeople > 0 ? 'warn' : 'done', lines };
  });

  const fillStatus = statusOf([data.regions], () => {
    if (simulated.length === 0) return { tone: 'warn', lines: ['Сначала назначьте шаблоны и население регионам'] };
    const purses = simulated.filter((r) => r.purse > 0).length;
    const reserve = simulated.filter((r) => r.treasury_target > 0 && r.treasury >= r.treasury_target).length;
    return {
      tone: purses === simulated.length && reserve === simulated.length ? 'done' : 'warn',
      lines: [
        `Кошельки жителей не пустые: ${purses} из ${simulated.length}`,
        `Казна не ниже резерва жалованья: ${reserve} из ${simulated.length}`,
      ],
    };
  });

  const merchantsStatus = statusOf([data.merchants], () => {
    const m = data.merchants.data as EconMerchantsResponse;
    if (m.items.length === 0) return { tone: 'info', lines: ['Торговцев пока нет — добавьте товары НПС на странице НПС'] };
    const living = m.items.filter((x) => x.living);
    const withTarget = living.filter((x) => x.cash_target > 0);
    const funded = withTarget.filter((x) => x.cash >= x.cash_target).length;
    const notSimulated = m.items.filter((x) => x.reason === 'not_simulated').length;
    const lines = [
      `Торговцев: ${m.items.length}, живых: ${living.length}`,
      `Кассы пополнены до нормы: ${funded} из ${withTarget.length}`,
    ];
    if (notSimulated > 0) lines.push(`Обычных, потому что регион не в пересчёте: ${notSimulated}`);
    if (living.length > withTarget.length)
      lines.push(`Живых без нормы кассы (нет рыночных товаров с нормой склада): ${living.length - withTarget.length}`);
    const tone: Tone = living.length === 0 ? 'warn' : funded === withTarget.length ? 'done' : 'warn';
    return { tone, lines };
  });

  const banksStatus = statusOf([data.banks, data.regions], () => {
    const b = data.banks.data as EconBanksResponse;
    const enabled = b.items.filter((x) => x.enabled);
    const bankersOf = (x: (typeof b.items)[number]) => (Array.isArray(x.bankers) ? x.bankers.length : Number(x.bankers) || 0);
    const noBanker = enabled.filter((x) => bankersOf(x) === 0).length;
    const noFunds = enabled.filter((x) => x.lendable <= 0).length;
    const bigWithoutBank = simulated.filter(
      (r) => r.template_code && BANK_TEMPLATES.includes(r.template_code) && !r.bank_enabled,
    ).length;
    const lines = [`Банков открыто: ${enabled.length}`];
    if (noBanker > 0) lines.push(`Банкиров нет в ${noBanker} — назначьте НПС роль «Банкир» в локации региона`);
    if (noFunds > 0) lines.push(`Без свободных денег: ${noFunds} — не смогут платить проценты и выдавать займы`);
    if (bigWithoutBank > 0) lines.push(`Столичных и портовых регионов в пересчёте без банка: ${bigWithoutBank}`);
    if (b.totals.debtors > 0) lines.push(`Просроченных займов: ${b.totals.debtors}`);
    const tone: Tone = enabled.length === 0 ? 'warn' : noBanker > 0 || noFunds > 0 ? 'warn' : 'done';
    return { tone, lines };
  });

  const tickStatus = statusOf([data.sim], () => {
    const s = data.sim.data as EconSimState;
    const last = latestRun(s.runs);
    const lines: string[] = [];
    let tone: Tone = 'done';
    if (!last) {
      lines.push('Пересчётов ещё не было');
      tone = 'warn';
    } else {
      lines.push(
        `Последний пересчёт: ${formatDateTime(last.started_at)} — ${RUN_STATUS_TEXT[last.status] ?? last.status}` +
          ` (регионов ${last.regions_done} из ${last.regions_total})`,
      );
      if (last.status === 'failed') tone = 'bad';
      else if (last.status === 'partial') tone = 'warn';
    }
    if (!s.env_enabled) {
      lines.push('Автопересчёт выключен на сервере (переменная окружения) — работает только «Пересчитать сейчас»');
      tone = tone === 'bad' ? 'bad' : 'warn';
    } else if (!s.tick_enabled) {
      lines.push('Автопересчёт по расписанию выключен');
      tone = tone === 'bad' ? 'bad' : 'warn';
    } else {
      lines.push(`Следующий по расписанию: ${formatDateTime(s.next_slot_at)}`);
    }
    return { tone, lines };
  });

  const eventsStatus = statusOf([data.sim], () => {
    const p = (data.sim.data as EconSimState).params;
    // A backend without the FEAT-187 params yet behaves as with the defaults.
    const enabled = (p.events_enabled ?? 1) === 1;
    const rate = p.event_rate_per_season ?? 1;
    const lines = [
      enabled
        ? `Автоматические события включены: в среднем ${formatDecimal(rate)} на регион за игровой сезон`
        : 'Автоматические события выключены — начинаются только запущенные вручную',
    ];
    const tone: Tone = enabled && rate > 0 ? 'done' : 'warn';
    return { tone, lines };
  });

  const mintStatus = statusOf([data.sim], () => {
    const p = (data.sim.data as EconSimState).params;
    // A backend without the FEAT-191 params yet behaves as with the defaults (all off).
    const quota = p.quota_season_amount ?? 0;
    const limit = p.mint_season_limit ?? 0;
    const lines = [
      quota > 0 ? `Квота сезона: ${format(quota, true)}` : 'Квота сезона не задана (0) — квоты нет',
      limit > 0
        ? `Лимит чеканки по умолчанию: ${format(limit, true)} на страну за сезон, порог двора ${formatDecimal(p.mint_court_threshold_pct ?? 100)} %`
        : 'Лимит чеканки по умолчанию 0 — двор и монетчики закрыты (кроме стран со своим лимитом)',
    ];
    const tone: Tone = quota > 0 || limit > 0 ? 'done' : 'info';
    return { tone, lines };
  });

  const caravansStatus = statusOf([data.caravans], () => {
    const c = data.caravans.data as CaravanOverview;
    const enabled = (c.params.caravans_enabled ?? 1) === 1;
    const open = c.pairs.filter((p) => p.is_enabled).length;
    const lines = [
      enabled ? 'Караваны включены' : 'Караваны выключены — новые не отправляются, идущие доезжают',
      c.pairs.length === 0
        ? 'Пар стран нет — караваны ходят только внутри стран'
        : `Пар стран с открытой торговлей: ${open} из ${c.pairs.length}`,
      `Караванов в пути: ${c.in_transit.count}`,
    ];
    if (!c.escrow.ok) lines.push('Счёт «Караваны в пути» расходится — см. «Сводку»');
    const tone: Tone = !c.escrow.ok ? 'bad' : enabled ? 'done' : 'warn';
    return { tone, lines };
  });

  const guildStatus = statusOf([data.sim], () => {
    const p = (data.sim.data as EconSimState).params;
    // A backend without the FEAT-193 params yet behaves as with the defaults (orders on).
    const enabled = (p.guild_enabled ?? 1) === 1;
    const cap = p.guild_xp_daily_cap ?? 200;
    const lines = [
      enabled
        ? `Заказы гильдии включены: надбавка ${formatDecimal(p.guild_markup_pct ?? 20)} %, порог ${formatDecimal(p.guild_open_threshold_pct ?? 80)} % нормы`
        : 'Заказы гильдии выключены — новые не открываются',
      cap > 0 ? `Опыт за сдачу: до ${cap} в сутки на персонажа` : 'Опыт за сдачу в гильдию выключен (лимит 0)',
      'Представителей гильдии в регионах проверьте во вкладке «Гильдия»',
    ];
    const tone: Tone = enabled ? 'info' : 'warn';
    return { tone, lines };
  });

  const invariantStatus: StepStatus = summary
    ? summary.invariant.ok
      ? { tone: 'done', lines: ['Сводка: «Сходится»', `Выпущено всего: ${big(summary.totals.issued, true)}${
              Math.abs(summary.totals.issued) >= COMPACT_MONEY_FROM ? ` (точно ${format(summary.totals.issued, true)})` : ''
            }`] }
      : { tone: 'bad', lines: ['Сводка: «Расхождение» — см. рецепт ниже'] }
    : summaryError
      ? errorStatus(summaryError)
      : loadingStatus;

  /* ----------------------------------------------------------------------------------------- steps */

  const steps: Step[] = [
    {
      title: 'Название валюты и доля страны',
      body: (
        <>
          Как валюта пишется во всей игре (одна марка, две марки, пять марок, сокращение) и какую долю налогов и
          платежей игроков в казну региона забирает страна. По умолчанию 10 %; можно от 0 до 50 %. Остальные сервисы
          подхватывают изменения в течение минуты.
        </>
      ),
      status: currencyStatus,
      actions: [{ label: 'Открыть «Настройки»', tab: 'settings' }],
    },
    {
      title: 'Группы товаров и предметов',
      body: (
        <>
          12 групп товаров (продовольствие, руда и металл, оружие…) общие для всех регионов: базовая цена, сколько
          нужно на 1000 жителей в день, из какого сырья делается. От базовых цен зависят стартовые кошельки жителей
          и закупочные цены торговцев, поэтому меняйте их <B>до</B> заполнения регионов. Во вкладке «Предметы»
          проверьте, что предметы, которые продают торговцы, попали в нужную группу: предмет без группы — вне рынка.
          Значения по умолчанию рабочие, их можно не трогать.
        </>
      ),
      status: groupsStatus,
      actions: [
        { label: 'Открыть «Товары»', tab: 'goods' },
        { label: 'Открыть «Предметы»', tab: 'items' },
      ],
    },
    {
      title: 'Шаблоны регионов',
      body: (
        <>
          Шаблон — заготовка региона: население, налог и что регион производит больше или меньше нормы. Есть 8
          шаблонов: Столичный регион (2.5 м жителей, налог 12 %), Портовый регион (1.2 м, 10 %), Шахтёрский регион
          (600 к, 10 %), Аграрный регион (800 к, 8 %), Лесной регион (400 к, 8 %), Магический регион (700 к, 12 %),
          Пограничный регион (300 к, 6 %), Сельский регион (250 к, 6 %). Население — лорное, как его видят игроки;
          пересчёт берёт его в масштабе 1 к 100 (параметр «Масштаб населения» во вкладке «Пересчёт»): 4.0 м жителей
          считаются как 40 000, 100 к — как 1 000. В списках население показано коротко («4.0 м», «120 к»), точное
          число — при наведении. Назначьте шаблон каждому региону, который должен «жить»: «Регионы» → регион → поле
          «Шаблон» → сохранить. При первом назначении региону копируются только товары шаблона: население
          впишите там же в поле «Население» (или поставьте галочку «Население из шаблона» на следующем шаге), а
          налог шаблона подставляет кнопка «Применить шаблон». Регион без шаблона или с населением 0 в пересчёте
          не участвует, его торговцы остаются обычными.
        </>
      ),
      status: templatesStatus,
      actions: [
        { label: 'Открыть «Шаблоны»', tab: 'templates' },
        { label: 'Открыть «Регионы»', tab: 'regions' },
      ],
    },
    {
      title: 'Заполнить регионы по шаблонам',
      body: (
        <>
          Кнопка во вкладке «Регионы». Заново копирует товары шаблона (ручные правки производства и потребления
          регионов сбрасываются), ставит запасы в норму и <B>выпускает новые деньги</B>:
          кошелёк жителей — до нормы богатства (по классам; без классов — 7 дней потребностей по базовым ценам), казну — до резерва жалованья (7 дней налогов).
          Галочка «Население из шаблона» (по умолчанию выключена) ставит население шаблона регионам, где оно 0 —
          без неё такие регионы пропускаются. Галочка «Открыть банки в столицах и портах» сразу включает банк
          регионам с шаблоном «Столичный регион» или «Портовый регион» и берёт ему стартовый капитал из казны. Галочки
          «Вернуть излишек кошелька жителей / казны в эмиссию» (по умолчанию выключены) забирают обратно всё, что выше
          стартового кошелька и резерва жалованья. Повторное нажатие доливает только недостающее. Нужны права
          economy:settings и economy:emit.
        </>
      ),
      status: fillStatus,
      actions: [{ label: 'Открыть «Регионы»', tab: 'regions' }],
    },
    {
      title: 'Торговцы: пополнить кассы',
      body: (
        <>
          Торговец — НПС с товарами в лавке (товары и «Норма склада» задаются на странице НПС). <B>Живым</B> он
          становится сам, если жив и стоит в локации региона, который участвует в пересчёте; иначе он «обычный»:
          цены как в лавке, деньги идут прямо в казну. У живого торговца своя касса, из неё он платит игрокам
          за скупку. Нажмите «Пополнить кассы торговцев» во вкладке «Торговцы» — касса каждого живого торговца
          дойдёт до нормы (новые деньги, повторный клик ничего лишнего не выпустит).
        </>
      ),
      status: merchantsStatus,
      actions: [
        { label: 'Открыть «Торговцы»', tab: 'merchants' },
        { label: 'Страница НПС', to: '/admin/npcs' },
      ],
    },
    {
      title: 'Банки и банкиры',
      body: (
        <>
          Банк — один на регион, включается галочкой «Банк есть» в редакторе региона или кнопкой «Открыть банк» во
          вкладке «Банки». При
          первом включении (с галочкой стартового капитала) банк один раз берёт капитал из казны региона (по умолчанию до{' '}
          {format(20000, true)}, но только из излишка казны сверх её резерва — казна не опускается ниже цели). Прибыль
          банка (полученные проценты минус выплаченные) каждый пересчёт уходит обратно в казну региона. Игроки пользуются банком через НПС с ролью «Банкир» —
          роль ставится на странице НПС, а сам НПС должен стоять в локации этого региона.
        </>
      ),
      status: banksStatus,
      actions: [
        { label: 'Открыть «Банки»', tab: 'banks' },
        { label: 'Страница НПС', to: '/admin/npcs' },
      ],
    },
    {
      title: 'События регионов',
      body: (
        <>
          Засухи, потопы, чума, праздники и ярмарки начинаются сами — в среднем одно событие на регион за игровой
          сезон. Готов стартовый набор из 14 событий с текстами для игроков; просмотрите его во вкладке «События» и
          выключите или поправьте то, что не подходит миру. Частота и пределы — в блоке «События» вкладки «Пересчёт».
        </>
      ),
      status: eventsStatus,
      actions: [
        { label: 'Открыть «События»', tab: 'events' },
        { label: 'Как работают события', section: 'events' },
      ],
    },
    {
      title: 'Монетный двор и квота сезона',
      body: (
        <>
          Необязательный шаг — новые деньги без ручной эмиссии. Квота: «Настройки» → «Квота сезона», сумма раз в
          сезон (49 дней) уходит в казны регионов ниже нормы богатства — по нехватке. Двор: во вкладке «Монетный двор» проверьте столицу
          каждой страны, добавьте в список руды предметы с курсом за штуку и задайте лимит чеканки за сезон. Поставьте
          НПС роль «Монетчик» в локации столицы — к нему игроки понесут руду. Внимание: если запас руды столицы
          выше «Порога двора», двор начнёт чеканить в первом же пересчёте и может выбрать лимит почти целиком —
          поднимите порог, если хотите оставить лимит игрокам. Пока квота и лимит равны 0, всё выключено.
        </>
      ),
      status: mintStatus,
      actions: [
        { label: 'Открыть «Монетный двор»', tab: 'mint' },
        { label: 'Открыть «Настройки»', tab: 'settings' },
        { label: 'Страница НПС', to: '/admin/npcs' },
        { label: 'Как работает двор', section: 'mint' },
      ],
    },
    {
      title: 'Открыть торговлю между странами (если нужно)',
      body: (
        <>
          Необязательный шаг. Караваны НПС сами возят товары из регионов, где их больше нормы, туда, где их меньше
          нормы, — внутри страны всегда, без пошлины. Между странами — только если вы открыли торговлю для этой пары
          стран: во вкладке «Караваны» → «Торговля между странами» поставьте галочку «торгуют» и задайте пошлину (по
          умолчанию 10 %). По умолчанию страны друг с другом не торгуют.
        </>
      ),
      status: caravansStatus,
      actions: [
        { label: 'Открыть «Караваны»', tab: 'caravans' },
        { label: 'Как открыть торговлю', section: 'recipe-caravans' },
        { label: 'Как работают караваны', section: 'caravans' },
      ],
    },
    {
      title: 'Гильдия торговцев (заказы регионов)',
      body: (
        <>
          Необязательный шаг. Регион, которому не хватает товара, в каждом пересчёте сам выставляет заказ в гильдии
          торговцев, а игроки сдают туда предметы нужной группы за марки и немного опыта. Чтобы заказы можно было
          выполнять, поставьте НПС с ролью «Гильдия торговцев» в регионы — по одному в каждый регион, где нужны
          заказы. Без представителя заказ в регионе есть, но сдать товар некому и в карточке региона он не
          показывается.
        </>
      ),
      status: guildStatus,
      actions: [
        { label: 'Открыть «Гильдия»', tab: 'guild' },
        { label: 'Страница НПС', to: '/admin/npcs' },
        { label: 'Как открыть гильдию', section: 'recipe-guild' },
        { label: 'Как работает гильдия', section: 'guild' },
      ],
    },
    {
      title: 'Первый пересчёт',
      body: (
        <>
          Нажмите «Пересчитать сейчас» во вкладке «Пересчёт» и посмотрите итог: сколько регионов посчитано, есть
          ли ошибки. Это настоящий дополнительный шаг мира (не пробный), расписание он не сдвигает. Дальше мир
          пересчитывается сам каждые 6 часов, если включён «Автопересчёт по расписанию».
        </>
      ),
      status: tickStatus,
      actions: [{ label: 'Открыть «Пересчёт»', tab: 'tick' }],
    },
    {
      title: 'Проверить сводку',
      body: (
        <>
          Во вкладке «Сводка» должна гореть зелёная метка «Сходится»: сумма всех счетов мира равна нулю, ставки и
          хранилище аукциона, вклады игроков и деньги караванов в пути совпадают со своими записями. «Выпущено» — сколько денег создано
          эмиссией и корректировками за всё время.
        </>
      ),
      status: invariantStatus,
      actions: [
        { label: 'Открыть «Сводка»', tab: 'summary' },
        { label: 'Если «Расхождение»', section: 'recipe-invariant' },
      ],
    },
  ];

  const runAction = (a: StepAction) => {
    if (a.section) onOpenSection(a.section);
    else if (a.tab) onOpenTab(a.tab);
  };

  const tocSections: GuideSectionId[] = [
    'checklist',
    'overview',
    'accounts',
    'money-flow',
    'tick',
    'regions',
    'merchants',
    'banks',
    'events',
    'mint',
    'caravans',
    'guild',
    'classes',
    'recipes',
  ];

  /* ---------------------------------------------------------------------------------------- render */

  return (
    <div className="flex flex-col gap-8">
      <nav className="flex flex-wrap gap-2" aria-label="Разделы гайда">
        {tocSections.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onOpenSection(s)}
            className="chip-outline rounded-full px-3 py-1.5 text-xs font-medium"
          >
            {GUIDE_SECTION_TITLE[s]}
          </button>
        ))}
      </nav>

      {/* ------------------------------------------------------------------------------ checklist */}
      <Section id="checklist">
        <div className="flex flex-col sm:flex-row sm:items-end gap-2">
          <H2>Чек-лист запуска</H2>
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="sm:ml-auto self-start inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-site-blue transition-colors duration-200 ease-site disabled:opacity-40"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Обновить статусы
          </button>
        </div>
        <P>
          Пройдите шаги сверху вниз. Статус каждого шага считается по текущим данным; после изменений нажмите
          «Обновить статусы».
        </P>
        {!canSettings && (
          <Note>
            У вас нет права economy:settings: статусы видны, но кнопки изменений на вкладках будут скрыты.
          </Note>
        )}
        {canSettings && !canEmit && (
          <Note>
            У вас нет права economy:emit: «Заполнить регионы по шаблонам» и «Пополнить кассы торговцев» будут скрыты.
          </Note>
        )}
        {!loading && loadErrors > 0 && (
          <p className="text-site-red text-sm">
            Часть данных не загрузилась ({loadErrors}) — статусы этих шагов не показаны, остальной гайд доступен.
          </p>
        )}

        <ol className="flex flex-col gap-3">
          {steps.map((step, i) => (
            <li key={step.title} className="gray-bg !rounded-card p-4 sm:p-5 flex flex-col gap-3">
              <div className="flex items-start gap-3">
                <span className="shrink-0 w-7 h-7 rounded-full border border-gold/50 text-gold text-sm flex items-center justify-center">
                  {i + 1}
                </span>
                <div className="flex flex-col gap-2 min-w-0">
                  <h3 className="text-white text-base font-medium">{step.title}</h3>
                  <p className="text-white/70 text-sm leading-relaxed">{step.body}</p>
                </div>
              </div>
              <div className="flex flex-col md:flex-row md:items-end gap-3 md:pl-10">
                <div className="flex items-start gap-2 min-w-0 flex-1">
                  {step.status ? (
                    <>
                      <span className="shrink-0 mt-0.5">{TONE_ICON[step.status.tone]}</span>
                      <div className="flex flex-col gap-0.5 min-w-0 text-sm">
                        <span className="text-white/50 text-xs uppercase tracking-[0.06em]">
                          {TONE_TEXT[step.status.tone]}
                        </span>
                        {step.status.lines.map((line) => (
                          <span key={line} className="text-white/85 break-words">
                            {line}
                          </span>
                        ))}
                      </div>
                    </>
                  ) : (
                    <>
                      <CircleDashed size={18} className="shrink-0 mt-0.5 text-white/40" />
                      <span className="text-white/50 text-sm">Статус не отслеживается — проверьте вручную</span>
                    </>
                  )}
                </div>
                <div className="flex flex-wrap gap-2 shrink-0">
                  {step.actions.map((a) =>
                    a.to ? (
                      <Link key={a.label} to={a.to} className="btn-line !text-xs !py-2 !px-4">
                        {a.label}
                      </Link>
                    ) : a.tab && !availableTabs.includes(a.tab) ? null : (
                      <button
                        key={a.label}
                        type="button"
                        onClick={() => runAction(a)}
                        className="btn-line !text-xs !py-2 !px-4"
                      >
                        {a.label}
                      </button>
                    ),
                  )}
                </div>
              </div>
            </li>
          ))}
        </ol>
      </Section>

      {/* ------------------------------------------------------------------------------ overview */}
      <Section id="overview">
        <H2>Как устроена экономика</H2>
        <P>
          Все деньги мира лежат на <B>счетах</B>. Деньги не появляются и не исчезают сами — они только переходят со
          счёта на счёт, и каждое движение записывается в «Журнал» как операция «откуда → куда». Новые деньги
          создаёт только админ — <B>эмиссией</B>. Поэтому сумма всех счетов (вместе со счётом «Эмиссия», который
          уходит в минус на выпущенную сумму) всегда равна нулю — это и проверяет метка «Сходится» в «Сводке».
        </P>
        <P>
          Регионы с шаблоном и жителями «живут»: каждые 6 часов жители производят и потребляют товары, платят налог
          и получают жалованье, торгуют с торговцами и пользуются банком. Игроки в этом участвуют через казны
          (награды, дома, телепорты), лавки торговцев и банки.
        </P>
      </Section>

      <Section id="accounts">
        <H3>Где лежат деньги</H3>
        <UL>
          <li>
            <B>Эмиссия</B> — источник всех новых денег. Её баланс отрицательный: минус ровно столько, сколько вы
            выпустили. «Выпущено» в «Сводке» — это эмиссия плюс ручные корректировки.
          </li>
          <li>
            <B>Казна региона</B> — получает налоги жителей, налог с выручки торговцев и платежи игроков в регионе;
            платит жалованье жителям и награды игрокам за бои и задания. Может уйти в минус («Казна в долгах») —
            это значит, что регион уже раздал больше, чем собрал.
          </li>
          <li>
            <B>Казна страны</B> — забирает свою долю (по умолчанию 10 %) с налогов и платежей игроков в казны её
            регионов (эмиссия не облагается) и каждые 6 часов раздаёт 25 % своих денег регионам как грант: четверть — регионам ниже нормы богатства по нехватке, остальное пропорционально числу жителей.
          </li>
          <li>
            <B>Казна Скитальцев</B> — общая казна мира: платит награды боевого пропуска, получает платежи в
            локациях без региона.
          </li>
          <li>
            <B>Кошелёк жителей</B> — общие деньги всех жителей региона (жители — не персонажи, а число «население»; считается в масштабе 1 к 100 от лорного).
            Большие суммы в админке показаны коротко («4.5 м» — 4 500 000), точная сумма — при наведении.
            На них жители покупают товары. В минус не уходит.
          </li>
          <li>
            <B>Касса торговца</B> — деньги конкретного НПС-торговца. Из неё он платит игрокам за скупку и
            докупает товар у региона. В минус не уходит: пустая касса — торговец не может купить.
          </li>
          <li>
            <B>Банк</B> — два счёта на регион. «Свои деньги банка»: капитал из казны, вклады жителей, погашения
            займов; из них выдаются займы и платятся проценты. «Хранилище вкладов игроков»: всегда ровно сумма
            вкладов игроков, никогда не идёт в займы — поэтому вклад игрока всегда можно снять.
          </li>
          <li>
            <B>Персонажи</B> — кошельки игроков и НПС; <B>Ставки и Хранилище аукциона</B> — деньги, временно
            лежащие на аукционе.
          </li>
          <li>
            <B>Караваны в пути</B> — один общий счёт: деньги, которые покупатели заплатили за караваны, ещё не
            доехавшие до места. При доставке они уходят продавцу (и пошлина — стране), при отмене возвращаются
            покупателю. В минус не уходит; всегда равен сумме оплаты караванов в пути.
          </li>
        </UL>
      </Section>

      <Section id="money-flow">
        <H3>Схема движения денег</H3>
        <div className="flex flex-wrap gap-2 text-xs">
          <Node kind="source">новые деньги</Node>
          <Node kind="treasury">казны</Node>
          <Node kind="people">жители</Node>
          <Node kind="business">торговцы и банки</Node>
          <Node kind="player">игроки</Node>
        </div>
        <div className="flex flex-col gap-5">
          <FlowGroup title="Админ (по кнопке)" flows={FLOWS_ADMIN} />
          <div className="flex justify-center text-white/30">
            <ArrowDown size={18} />
          </div>
          <FlowGroup title="Каждые 6 часов (сами)" flows={FLOWS_TICK} />
          <div className="flex justify-center text-white/30">
            <ArrowDown size={18} />
          </div>
          <FlowGroup title="Игроки (когда играют)" flows={FLOWS_PLAYERS} />
        </div>
        <Note>
          Главный круг: кошелёк жителей → налог → казна региона → жалованье → кошелёк жителей. С каждого налога
          10 % уходит в казну страны и возвращается в регионы грантом. Если казна платит игрокам больше, чем
          получает, деньги уходят из круга к игрокам — следите за казнами.
        </Note>
      </Section>

      <Section id="tick">
        <H3>Что происходит каждые 6 часов</H3>
        <P>
          Пересчёт идёт в 00:00, 06:00, 12:00 и 18:00 по UTC (03, 09, 15 и 21 по Москве). Пропущенный пересчёт
          (сервер был выключен) не догоняется. Для каждого региона с шаблоном и жителями — один шаг длиной в
          четверть дня:
        </P>
        <OL>
          <li>
            <B>Производство.</B> Каждая группа производит «производство на 1000 жителей» × расчётное население (лорное ÷ 100). Меньше —
            при низкой стабильности (ниже 60 производство падает, до половины при 0) и при голоде (до −50 %).
            Готовые товары тратят сырьё: оружие — 3 руды, зелья — 2 травы и т. п.
          </li>
          <li>
            <B>Покупки жителей.</B> Жители хотят норму потребления; богатые хотят больше (особенно роскоши),
            дорогие товары берут меньше. Если в кошельке меньше, чем стоит день потребностей, покупают
            пропорционально меньше.
          </li>
          <li>
            <B>Голод</B> — насколько не хватило еды до нормы (0 — сыты, 100 % — еды не было).
          </li>
          <li>
            <B>Цены.</B> Множитель цены группы зависит от запаса относительно нормы: запас равен норме — ×1, запас
            вдвое меньше — примерно ×1,55, вдвое больше — примерно ×0,65. Границы ×0,5 … ×3. Запас выше трёх норм
            портится.
          </li>
          <li>
            <B>Налог и жалованье.</B> «Доход» — стоимость произведённого. Налог = доход × ставка региона (но не
            больше кошелька) идёт из кошелька в казну, 10 % из него — стране. Жалованье = налог за вычетом доли
            страны + грант + 1/8 от того, насколько казна выше резерва (если ниже — жалованье меньше, и казна
            копит). Резерв = 7 дней налогов.
          </li>
          <li>
            <B>Стабильность</B> тянется к 85 минус штрафы: голод (до −100), нехватка товаров (до −15), налог выше
            12 % (−2 за каждый процент сверх), казна в минусе (−10). Падает быстро, растёт медленно.
            <B> Достаток</B> тянется к значению от того, хватает ли жителям товаров, сколько денег в кошельке
            (относительно 14 дней потребностей) и какая стабильность; голод его снижает.
          </li>
          <li>
            <B>Торговцы</B> региона: жители покупают у них (вместе не больше 5 % кошелька за шаг), торговец платит
            налог с выручки в казну и докупает товар у региона по оптовой цене (половина цены), деньги за товар
            уходят жителям.
          </li>
          <li>
            <B>Банки</B> (после всех регионов): проценты по вкладам, проценты по займам, вклады и займы жителей,
            взыскание просроченных займов.
          </li>
        </OL>
        <P>
          Перед всеми регионами — <B>события</B>: истёкшие заканчиваются, в плановом пересчёте могут начаться новые;
          идущие события меняют шаги выше (производство, цены, стабильность…). Подробно — в разделе «События
          регионов».
        </P>
        <P>
          Затем, тоже перед регионами, — <B>караваны</B>: сначала приезжают те, что в пути, потом отправляются новые.
          Поэтому шаг региона уже считает цены и потребление по запасу после караванов. Подробно — в разделе
          «Караваны НПС».
        </P>
        <P>
          «Пересчитать сейчас» делает ещё один такой же шаг немедленно (новых событий он не бросает, а караваны
          двигает так же, как плановый). Подсказки к каждому параметру — во вкладке «Пересчёт».
        </P>
      </Section>

      <Section id="regions">
        <H3>Жители, товары и цены</H3>
        <UL>
          <li>
            <B>Норма запаса</B> группы = дни запаса группы × (потребление жителей в день + сырьё для производства в
            день). Пример: продовольствие — 300 единиц на 1000 жителей в день, запас на 7 дней; в Столичном регионе
            на 2.5 м жителей (в расчёте 25 000) это 7 500 единиц в день и норма 52 500.
          </li>
          <li>
            <B>Стартовый кошелёк</B> при заполнении — норма богатства (около 6–10 дней потребностей по базовым ценам, по классам; без классов — 7 дней). Только еда Столичного региона стоит
            7 500 × {format(2, true)} = {format(15000, true)} в день.
          </li>
          <li>
            <B>Производство шаблона</B>: больше 1 — специализация (Шахтёрский регион: руда ×2), меньше 1 — хроническая
            нехватка (Пограничный регион: еда ×0,85). Нехватку регион компенсирует ценой: дорогой товар меньше
            покупают и больше производят.
          </li>
          <li>
            Игрок видит у региона только слова («Регион сыт», «Цены высокие», «Казна в порядке»), без чисел.
          </li>
        </UL>
      </Section>

      <Section id="merchants">
        <H3>Торговцы НПС</H3>
        <UL>
          <li>
            <B>Живой торговец</B> — НПС жив, стоит в локации (не в подземелье) региона в пересчёте. Статус
            проверяется при каждом запросе: увели НПС или убрали шаблон — сразу «обычный».
          </li>
          <li>
            <B>Цены</B>: в лавке задаются базовые; живой торговец умножает их на множитель цены группы в регионе.
            Скидка за харизму — до 50 %. Скупка у игрока — не дороже половины цены продажи, чтобы перепродажа тому
            же торговцу была невыгодна.
          </li>
          <li>
            <B>Склад</B>: у живого торговца товар кончается; каждые 6 часов он докупает его у региона до «Нормы
            склада», если в регионе есть запас группы и в кассе — деньги.
          </li>
          <li>
            <B>Норма кассы</B> = 2 × стоимость полной закупки (норма склада × оптовая цена). Пример: 10 мечей с
            базовой ценой {format(100, true)} — опт {format(50, true)}, полная закупка {format(500, true)}, норма
            кассы {format(1000, true)}. Касса выше трёх норм понемногу отдаётся жителям.
          </li>
          <li>
            <B>Обычный торговец</B> работает как раньше: цены как в лавке (×1), пустой запас — без ограничений,
            игрок платит в казну региона, скупка оплачивается из казны.
          </li>
          <li>Предмет вне рынка (без группы, свитки, рецепты, легендарные и выше) живой торговец не докупает.</li>
        </UL>
      </Section>

      <Section id="banks">
        <H3>Банки</H3>
        <UL>
          <li>
            <B>Вклад до востребования</B>: 0,1 % в день (около 3 % в месяц), снимается в любой момент.{' '}
            <B>Срочный</B> на 7 / 14 / 28 дней: 0,2 / 0,25 / 0,3 % в день (около 6 / 7,5 / 9 % в месяц), ставка
            фиксируется при открытии.
          </li>
          <li>
            <B>Займ</B>: 0,5 % в день (около 15 % в месяц), на 7 / 14 / 28 дней, не больше {format(500, true)} +{' '}
            {format(250, true)} за каждый уровень персонажа. Просрочка: +1 % в день сверху, долг перестаёт расти на
            двух суммах займа. Просроченный долг банк взыскивает сам: со вкладов должника, затем с кошелька.
          </li>
          <li>
            <B>Ставки вкладов гибкие</B>: если доход банка от займов меньше 1,25 × его расходов на проценты по
            вкладам, ставки вкладов плавно снижаются (до 20 % от базовых).
          </li>
          <li>
            <B>Проценты платятся только из свободных денег</B> банка: свои деньги минус резерв 20 % от вкладов
            жителей. Не хватает — каждому платится часть, остальное за этот шаг сгорает; нет свободных денег —
            проценты не платятся.
          </li>
          <li>
            Перевод между банками или другому игроку — комиссия 2 % (не меньше {format(1, true)}). Минимальная
            сумма операции — {format(10, true)}.
          </li>
          <li>Жители держат в банке около 20 % своих денег и берут займы примерно на 10 % кошелька.</li>
        </UL>
      </Section>

      <Section id="events">
        <H3>События регионов</H3>
        <P>
          Событие — временная беда или удача региона: засуха, потоп, чума, набег, бунт, урожайный год, ярмарка,
          праздник… Событие само ничего не «рисует» — оно на время подкручивает обычные рычаги расчёта, а дальше
          экономика доделывает остальное: засуха урезает урожай → еды меньше → цены растут → голод → падает
          стабильность → если долго, вспыхивает бунт.
        </P>
        <P>
          <B>Что видят игроки.</B> В карточке региона на странице мира: иконка, название, художественный текст и
          сколько ещё продлится («ещё 6 дн.», «ещё 5 ч»). Цифр эффектов игроки не видят — только последствия: цены у
          торговцев, слова о голоде, беспорядках и ценах в той же карточке.
        </P>
        <P>
          <B>Шаблоны</B> («{TAB_NAME.events}» → «Шаблоны»). Поставляется готовый набор из 14 событий: 8 плохих
          (засуха, потоп, чума, магическая катастрофа, обвал в шахте, мор скота, набег, бунт) и 6 хороших (урожайный
          год, благоприятная магическая аномалия, богатая жила, ярмарка, праздник, удачный улов). У шаблона есть
          иконка, текст для игроков, длительность (диапазон в днях), область, эффекты, в каких шаблонах регионов и в
          какие сезоны оно случается, вес и шанс распространиться. Правка шаблона действует только на новые
          запуски — уже идущие события живут по копии шаблона на момент старта.
        </P>

        <H3>Эффекты</H3>
        <UL>
          <li>
            <B>Каждый пересчёт, пока идёт событие:</B> производство группы ×N; потребление (спрос) группы ×N;
            «больные жители» — производство всех групп ×N; цена группы ×N (в пределах обычных границ цены); налог в
            казну ×N; стабильность и достаток ± за пересчёт (4 раза в день — −2 за пересчёт это −8 в день);
            торговцы не докупают товар; банк: паника (жители забирают вклады, вклады игроков не трогаются) или бум
            займов.
          </li>
          <li>
            <B>Разово:</B> потеря доли запасов групп; расход доли казны «на восстановление» (деньги уходят жителям
            региона проводкой «Событие региона» в журнале — не исчезают; пустая казна или долг — ничего не
            списывается); население ±% — <B>навсегда</B>. Разовые эффекты срабатывают один раз в первом
            пересчёте после начала события.
          </li>
          <li>
            <B>Несколько событий сразу</B> складываются: множители одной группы перемножаются (засуха — еда ×0,5,
            чума — ×0,75 → еда ×0,375), прибавки стабильности и достатка суммируются. Итог ограничен пределами из
            блока «События» во вкладке «{TAB_NAME.tick}» (по умолчанию множитель от ×0,1 до ×3, прибавка не больше
            ±10 за пересчёт). Одно и то же событие дважды в одном регионе идти не может.
          </li>
        </UL>

        <H3>Когда события начинаются</H3>
        <UL>
          <li>
            <B>Случайно.</B> Только в плановых пересчётах (раз в 6 часов): у каждого региона маленький шанс, в среднем
            выходит <B>одно событие на регион за игровой сезон</B> (сезон с праздником — 49 реальных дней). Выпавший
            регион получает одно из подходящих событий по весу: подходят включённые события со способом запуска
            «Случайно», подходящие его шаблону и текущему сезону игрового календаря. Если в регионе уже идут 3 события
            (параметр «Предел событий в регионе»), новые сами не приходят. Если календарь в этот момент недоступен,
            могут начаться только события без сезонов.
          </li>
          <li>
            <B>«Пересчитать сейчас» новых событий не бросает</B> и идущие не ускоряет: длительность — реальное время
            (6 дней — это 6 суток по часам), а не число пересчётов. Ручной пересчёт только заканчивает истёкшие и
            применяет разовые эффекты только что запущенных.
          </li>
          <li>
            <B>Вручную</B> («{TAB_NAME.events}» → «Запустить»): любое событие, даже выключенное, на регион, соседей,
            страну или весь мир; можно задать точную длительность. Регионы, где такое событие уже идёт, пропускаются.
            Разовые эффекты — в ближайшем пересчёте (или сразу по «Пересчитать сейчас»).
          </li>
          <li>
            <B>Распространение.</B> У шаблона шанс за всё время события перекинуться на один соседний регион
            (соседи — по переходам между регионами; если переходов нет — регионы той же страны). Перекинувшееся может
            пойти дальше, но не глубже «Глубины распространения» (по умолчанию 2 шага).
          </li>
          <li>
            <B>Цепочки.</B> Событие может с некоторым шансом вызвать другое: потоп → чума (30 %), засуха → мор скота
            (15 %). Цепочки не смотрят на сезоны и шаблоны регионов, но учитывают предел событий в регионе.
          </li>
          <li>
            <B>Бунт</B> не случаен: он начинается, когда стабильность региона держится ниже 25 три реальных дня подряд
            (параметры «Порог бунта» и «Бунт через»). Засуха и голод ведут к бунту сами — через стабильность. После
            конца бунта отсчёт начинается заново.
          </li>
        </UL>

        <H3>Отмена и история</H3>
        <UL>
          <li>
            «Отменить» (с комментарием) останавливает эффекты «каждый пересчёт» со следующего пересчёта.{' '}
            <B>Разовые последствия не откатываются</B>: погибшие жители, потерянные запасы и потраченная казна
            остаются. Вернуть их можно обычными инструментами — население в редакторе региона, эмиссия или
            корректировка во вкладке «Действия».
          </li>
          <li>
            Изменение населения записывается в историю события («было → стало») и меняет лорное население навсегда.
            Ниже одного расчётного жителя оно не опускается, регион из пересчёта не выпадает. Учтите: если потом
            нажать «Заполнить регионы по шаблонам» с «Вернуть излишек…», у сократившегося региона излишек кошелька
            и казны уйдёт в эмиссию.
          </li>
          <li>
            Все события — и идущие, и закончившиеся — хранятся навсегда во вкладке «{TAB_NAME.events}» → «История»
            (позже их будет читать газета).
          </li>
        </UL>
        <P>
          Если событий слишком много или их нет совсем — см. рецепт «Событий слишком много, мало или нет».
        </P>
      </Section>

      {/* ------------------------------------------------------------------------------ mint and quota (FEAT-191) */}
      <Section id="mint">
        <H3>Монетный двор и квота сезона</H3>
        <P>
          Кроме ручной эмиссии, у мира два штатных источника новых денег. Оба считают время <B>сезонами</B>: сезон
          игрового календаря вместе с праздником после него — 49 реальных дней, 4 сезона в год. Деньги выходят со
          счёта эмиссии обычными проводками, сумма мира остаётся равной нулю.
        </P>
        <UL>
          <li>
            <B>Квота сезона</B> («{TAB_NAME.settings}» → «Квота сезона»). Один раз в начале каждого сезона первый
            пересчёт, в котором хоть один регион <B>ниже нормы</B> (деньги жителей + казна меньше нормы богатства +
            резерва казны, см. «{GUIDE_SECTION_TITLE.classes}»), выпускает квоту в казны только таких регионов —
            пропорционально нехватке и не больше самой нехватки; остаток квоты не выпускается. Если ниже нормы
            никого — квота ждёт, каждый пересчёт сезона проверяет снова. Второй раз за сезон квота не выдаётся;
            пропущенные сезоны не догоняются. 0 — квоты нет. История выдач — во вкладке «{TAB_NAME.mint}».
          </li>
          <li>
            <B>Монетный двор</B> — один на страну, в её <B>столице</B>. Столица по умолчанию — единственный регион
            страны с шаблоном «столица»; если таких нет или их несколько, выберите столицу вручную во вкладке «
            {TAB_NAME.mint}», иначе страна не чеканит. Столица должна участвовать в пересчёте.
          </li>
          <li>
            <B>Двор сам</B>, в каждом пересчёте: если запас «Руда и металл» столицы выше порога (по умолчанию 100 %
            нормы запаса), забирает излишек сверх порога и чеканит его по курсу «денег за единицу». Деньги уходят в{' '}
            <B>казну страны</B> и до регионов доходят обычной дотацией страны — начиная со <B>следующего</B>{' '}
            пересчёта (план дотаций фиксируется в начале пересчёта). Если запас столицы уже выше порога, двор
            начнёт чеканить в первом же пересчёте после того, как вы зададите лимит, и может выбрать его почти
            целиком — тогда игрокам почти ничего не останется. Хотите оставить лимит игрокам — поднимите порог
            (например, до 150 %); двор простаивает — опустите.
          </li>
          <li>
            <B>Игроки</B> приносят руду <B>монетчику</B> — НПС с ролью «Монетчик», стоящему в локации столицы
            (поставьте его на странице НПС). Нужен пост с обращением к нему, мёртвый монетчик не работает. Какая
            руда годится и сколько за штуку платят — список руды во вкладке «{TAB_NAME.mint}». Сданная руда
            пополняет запас «Руда и металл» столицы; деньги — сразу в кошелёк, в журнале — «Чеканка». Чеканка
            засчитывается как заработок в заданиях боевого пропуска.
          </li>
          <li>
            <B>Лимит сезона</B> — общий на страну для двора и игроков (по умолчанию из параметров, у страны может
            быть свой). Исчерпан — двор не чеканит, монетчик отказывает до начала следующего сезона. Если игрок
            приносит больше, чем влезает в лимит, монетчик принимает сколько влезает, а остальная руда остаётся у
            игрока.
          </li>
        </UL>
        <Note>
          По умолчанию квота и лимит равны 0 — всё выключено, пока вы не зададите суммы. Изменение квоты, лимитов,
          курса двора и списка руды создаёт новые деньги, поэтому требует права на эмиссию.
        </Note>
      </Section>

      {/* ------------------------------------------------------------------------------ caravans (FEAT-192) */}
      <Section id="caravans">
        <H3>Караваны НПС</H3>
        <P>
          Караваны выравнивают запасы и цены между регионами: везут товар оттуда, где его больше нормы (он там
          дешёвый), туда, где его меньше нормы (он там дорогой). Ходят все 12 групп товаров. Деньги при этом только
          переходят со счёта на счёт — новые не появляются, сумма мира остаётся равной нулю.
        </P>
        <UL>
          <li>
            <B>Когда.</B> В каждом пересчёте — и плановом, и по «Пересчитать сейчас» — до шага регионов: сначала
            приезжают караваны в пути, потом отправляются новые. Несколько ручных пересчётов подряд заставляют
            караваны ехать быстрее по часам — пересчёт есть пересчёт.
          </li>
          <li>
            <B>Куда можно.</B> Внутри страны — между любыми регионами, которые участвуют в пересчёте (не только
            соседями), всегда. Между странами — только если во вкладке «{TAB_NAME.caravans}» для этой пары стран
            стоит галочка «торгуют» (одна на обе стороны); по умолчанию страны не торгуют.
          </li>
          <li>
            <B>Кто продаёт.</B> Регион, у которого запас группы выше нормы. За один пересчёт он отдаёт караванам не
            больше 25 % излишка этой группы («Доля излишка продавца»), у него всегда остаётся не меньше нормы.
            Решение принимается по запасу относительно нормы, а не по цене: скидка ярмарки сама по себе караванов не
            вызывает.
          </li>
          <li>
            <B>Кто покупает.</B> Регион, у которого запас группы вместе с уже едущими к нему караванами ниже нормы;
            покупает не больше, чем нужно до нормы. Сначала закупается продовольствие, первыми обслуживаются регионы,
            где нехватка сильнее; продавца берут сначала ближнего (своя страна раньше чужой), потом — дешёвого.
            Регион, который ещё ни разу не пересчитывался (норма 0), эту группу не продаёт и не покупает.
          </li>
          <li>
            <B>Цена</B> — базовая цена группы × множитель цены у продавца на момент отправки (с учётом его событий).
          </li>
          <li>
            <B>Кто и когда платит.</B> Платят жители покупателя из своего кошелька — при отправке, на счёт «Караваны
            в пути». За пересчёт караваны тратят не больше 25 % кошелька жителей («Доля кошелька покупателя»). Если
            жителям не хватает на <B>продовольствие</B>, недостающее доплачивает казна региона-покупателя — не больше
            50 % её положительного остатка за пересчёт; казна в минусе не платит. Прочие товары — только из кошелька.
            Не хватает денег — караван везёт столько, сколько оплачено. Продавец (кошелёк его жителей) получает
            деньги, только когда караван доехал.
          </li>
          <li>
            <B>Пошлина</B> — только между странами, процент задаётся для каждой пары (по умолчанию 10 %). Платят
            жители покупателя <B>сверх</B> цены (продавец получает полную цену), пошлина при доставке уходит в казну
            страны-покупателя. Внутри страны пошлины нет. Караваны не облагаются долей страны с поступлений в казну
            региона.
          </li>
          <li>
            <B>Время в пути.</B> Внутри страны — 1 пересчёт: отправлен в этом пересчёте, приезжает в следующем
            (до шага регионов). Между странами — 2 пересчёта. Пока караван едет, товар ни у кого: его не едят и не
            продают торговцы, у продавца он уже списан, у покупателя ещё не появился. Время в пути и пошлина
            записываются при отправке.
          </li>
          <li>
            <B>Набег и бунт.</B> Регион, где идёт событие, при котором торговцы не докупают товар («Набег», «Бунт»),
            не отправляет караваны, но может их получать (например, еду после набега). Караваны, которые уже в пути,
            доезжают.
          </li>
          <li>
            <B>Закрыли торговлю, пока караван в пути</B> — он всё равно доезжает и платит пошлину, записанную при
            отправке.
          </li>
          <li>
            <B>Отмена.</B> Если регион назначения вышел из пересчёта или удалён, караван отменяется: товар
            возвращается в регион-продавец, деньги полностью возвращаются тем, кто платил (кошельку жителей и казне
            региона; если регион удалён — казне его страны). Если удалён регион-продавец, караван всё равно доезжает,
            а деньги за товар уходят в казну страны продавца. Только если исчезли <B>оба</B> региона, товар
            списывается — деньги и тогда возвращаются.
          </li>
          <li>
            <B>Руда в столицы.</B> Караваны возят и «Руду и металл»: руда, приехавшая в столицу, в том же пересчёте
            может пойти в монетный двор — так задумано.
          </li>
          <li>
            <B>Пределы.</B> Сделки дешевле {format(10, true)} не отправляются; за пересчёт по всему миру — не больше
            200 караванов. Если выключить «Караваны» в параметрах, новые не отправляются, а идущие доезжают.
          </li>
          <li>
            <B>Что видят игроки.</B> В карточке региона на странице мира — только слова, без чисел: «Везут
            продовольствие из …», «Привезли …», «Вывозят руду в …», «Вывезли …», с пометкой «в пути» у тех, что
            ещё едут. Доставленные караваны показываются сутки. Цифры — только во вкладке «{TAB_NAME.caravans}».
          </li>
        </UL>
        <Note>
          История караванов хранится навсегда (позже её будет читать газета). В журнале операции караванов — «Караван:
          оплата», «Караван: доставка» и «Караван: возврат».
        </Note>
      </Section>

      {/* ------------------------------------------------------------------------------ guild orders (FEAT-193) */}
      <Section id="guild">
        <H3>Гильдия торговцев</H3>
        <P>
          Заказы гильдии дают игрокам способ закрывать нехватки регионов своими предметами. Заказы выставляют только
          регионы (заказов игроков друг другу нет), общей доски по миру нет — игрок узнаёт о заказах в карточке
          региона («Гильдия ищет: древесину, зелья») и у представителя гильдии. Новых денег заказы не создают: платят
          жители региона из своего кошелька.
        </P>
        <UL>
          <li>
            <B>Когда открывается заказ.</B> В каждом пересчёте, в конце шага региона: если запас группы вместе с уже
            едущими в регион караванами ниже 80 % нормы («Порог открытия заказа»). Объём — до <B>полной</B> нормы
            (минус караваны в пути, чтобы жители не платили дважды за одну нехватку). Нехватка дешевле{' '}
            {format(50, true)} по местной цене заказа не открывает. Если нехватка ушла или платить нечем, заказ
            закрывается сам; выполненный заказ закрывается сразу, а при сохранившейся нехватке в следующем пересчёте
            открывается новый.
          </li>
          <li>
            <B>Что принимают.</B> Любой предмет нужной группы — только обычные стопки без заточки, камней и износа.
            Не принимаются свитки, рецепты, квестовые предметы, всё легендарное и выше и предметы «вне рынка».
            Предмет с ценой 0 оценивается по базовой цене своей группы.
          </li>
          <li>
            <B>Цена за штуку</B> — ценность предмета × множитель цены региона + надбавка (по умолчанию 20 %). Но не
            ниже того, что за предмет заплатил бы торговец региона, и — если предмет продаёт торговец этого региона —
            не выше половины его самой дешёвой цены (с максимальной скидкой за харизму купить дешевле нельзя, так что
            «купил у торговца → сдал гильдии» всегда в минус). Перевозка из дешёвого региона в дорогой выгодна — так
            задумано.
          </li>
          <li>
            <B>Кто платит.</B> Кошелёк жителей: за пересчёт гильдия тратит не больше 25 % кошелька («Доля кошелька
            жителей»). За продовольствие при нехватке денег у жителей доплачивает казна региона — не больше 25 % её
            положительного остатка за пересчёт. Бюджет задаётся заново каждый пересчёт и не копится.
          </li>
          <li>
            <B>Сколько примут.</B> Целыми штуками, пока заказу ещё что-то нужно — последняя штука может немного
            перекрыть заказ. Если не хватает объёма или денег жителей, гильдия берёт сколько может, остальное
            остаётся у игрока. Личных лимитов нет: кто первый принёс, тот и получил.
          </li>
          <li>
            <B>Опыт.</B> Как за квест: 10 % от полученных марок, 5 % — за предметы, которые продают торговцы региона.
            Не больше 200 опыта в сутки на персонажа по обеим ставкам вместе; книга опыта заданий умножает его, лимит
            считается до книги. Боевой пропуск засчитывает марки за заказы как заработанные.
          </li>
          <li>
            <B>Где сдавать.</B> У НПС с ролью «Гильдия торговцев» в локации этого региона. Мёртвый представитель
            заказы не принимает.
          </li>
        </UL>
        <Note>
          История заказов хранится. В журнале операция — «Заказ гильдии». Монетный двор: если «Порог двора» ниже
          порога заказа, в столице может открыться заказ на руду, которую двор тут же чеканит, — поднимите порог двора.
        </Note>
      </Section>

      {/* ------------------------------------------------------------------------------ social classes (FEAT-194) */}
      <Section id="classes">
        <H3>Классы жителей и норма богатства</H3>
        <P>
          У каждого региона в пересчёте есть доли трёх классов — <B>бедные</B>, <B>зажиточные</B> и <B>богатые</B>, в
          сумме 100 %. Стартовые доли задаёт шаблон (столица — больше богатых, сельская округа — больше бедных), их
          можно поправить в редакторе региона. Классы не меняют, сколько регион производит, — они меняют, что и
          сколько жители покупают, сколько платят и сколько денег им «положено».
        </P>
        <UL>
          <li>
            <B>Спрос.</B> У каждой группы товаров — вес на душу для каждого класса («{TAB_NAME.goods}» → группа →
            «Спрос по классам»): бедные — еда и быт, богатые — украшения, магия, всё дорогое. Спрос считается{' '}
            <B>относительно долей шаблона</B>: регион с долями шаблона потребляет ровно как раньше; стало больше
            богатых — растёт спрос на роскошь. Изменение долей шаблона сдвигает баланс сразу у всех его регионов.
          </li>
          <li>
            <B>Норма богатства.</B> Сколько денег должно быть у жителей: каждому классу — столько дней его
            потребностей по базовым ценам (по умолчанию бедным 3, зажиточным 7, богатым 21). Поэтому норма столицы
            примерно в 1,7 раза выше нормы сельской округи — «столица остаётся богатой, бедный край — бедным».
            «Заполнить регионы» пополняет кошельки до этой нормы.
          </li>
          <li>
            <B>Покупательная способность.</B> Кошелёк делится между классами пропорционально их нормам. При росте
            цен или тонком кошельке первыми перестают покупать бедные; при нехватке товара его раскупают сначала
            богатые, потом зажиточные, потом бедные — голод бьёт по бедным первым.
          </li>
          <li>
            <B>Налог.</B> Обычный налог взвешен по классам (бедные почти не платят, богатые — вдвое больше
            зажиточных), тоже относительно долей шаблона. Сверх того — <B>налог с накоплений</B>: 2 % денег жителей
            сверх нормы за пересчёт уходят в казну региона (в журнале — в той же проводке «Пересчёт региона», 10 % из
            неё, как с любого налога, — стране).
          </li>
          <li>
            <B>Деньги не исчезают.</B> Налог с накоплений не возвращается жалованьем в том же пересчёте — казна
            отдаёт излишок медленно, через обычный возврат сверх резерва. Доля страны уходит в казну страны и
            дальше дотациями: 25 % пула («Дотация по нехватке») делится между регионами ниже нормы, остальное — по
            населению. Излишек так растекается по стране, но регионы не выравниваются — у них разные нормы.
          </li>
          <li>
            <B>Стабильность.</B> Больше 60 % бедных — недовольство; голод бедных бьёт по стабильности сильнее;
            богатые недовольны налогом выше 12 %. При долях шаблона и обычном налоге эти штрафы равны нулю.
          </li>
          <li>
            <B>Доли двигаются сами</B>, медленно: сигнал из достатка, денег относительно нормы, стабильности и голода.
            Сильный подъём поднимает около 3 п. п. бедных в зажиточные за сезон, голод опускает быстрее. Слабый
            сигнал (обычный регион) никого не двигает. Деньги выше нормы толкают вверх, но вместе с богатыми растёт и
            норма — регион оседает в составе, который его деньги держат, а не копит бесконечно. Доли не выходят за
            2–90 %.
          </li>
          <li>
            <B>Квота и дотация по нехватке.</B> Нехватка = норма богатства + резерв казны − кошелёк − казна. Квота
            сезона идёт только регионам с нехваткой (см. «{GUIDE_SECTION_TITLE.mint}»), четверть дотации страны —
            тоже.
          </li>
          <li>
            <B>События.</B> Эффект «Сдвиг классов» разово сдвигает доли: «Бунт», «Набег», «Чума» и новое «Разорение»
            — вниз, «Богатая жила» и «Ярмарка» — вверх. В истории события — доли до и после.
          </li>
          <li>
            <B>Что видят игроки.</B> Только слова: «Зажиточный город, много бедняков» и полоску из трёх цветов
            (бедные — много / средне / мало …). Никаких процентов — их не отдаёт даже сервер.
          </li>
        </UL>
        <Note>
          Где смотреть: «{TAB_NAME.regions}» — доли, сдвиг за пересчёт, деньги относительно нормы; редактор региона
          — доли, отчёт по классам (норма и деньги на жителя, сколько каждый класс может купить, нехватка). «Применить
          шаблон» сбрасывает доли к шаблону; «Заполнить регионы» их сохраняет, если не отмечено «Сбросить и классы».
          Все коэффициенты — «{TAB_NAME.tick}» → «Классы жителей и норма богатства»; там же аварийный выключатель
          (0 — расчёт как до классов).
        </Note>
      </Section>

      {/* ------------------------------------------------------------------------------ recipes */}
      <Section id="recipes">
        <H2>Что делать, если…</H2>
      </Section>

      <Section id="recipe-hunger">
        <H3>Голод в регионе</H3>
        <P>Голод бьёт по производству (до −50 %) и стабильности (до −100). Причин две — посмотрите в редакторе региона:</P>
        <OL>
          <li>
            <B>Мало еды</B> (запас «Продовольствия» ниже нормы, цена выше ×1): поднимите производство еды у региона
            или в его шаблоне, или смените шаблон. Разово — «Заполнить регионы по шаблонам» с галочкой «Запасы — к
            норме» (но она вернёт производство к шаблону — ручную правку региона после неё повторите). Учтите:
            Пограничному региону своей еды не хватает специально.
          </li>
          <li>
            <B>Еда есть, но жителям не на что купить</B> (кошелёк меньше дня потребностей): «Заполнить регионы по
            шаблонам» доведёт кошелёк до нормы богатства; проверьте казну — если она ниже резерва, жалованье урезано (см.
            «Пустая казна»).
          </li>
        </OL>
      </Section>

      <Section id="recipe-empty-treasury">
        <H3>Пустая казна</H3>
        <UL>
          <li>
            Казна ниже резерва → жалованье меньше налога, кошелёк жителей тает. Казна в минусе → стабильность −10.
          </li>
          <li>
            Быстро: «Заполнить регионы по шаблонам» с галочкой «Пополнить казну до резерва жалованья» или «Действия» →
            «Эмиссия» в казну региона.
          </li>
          <li>
            Для всех регионов страны сразу: эмиссия в казну страны — каждые 6 часов 25 % её денег раздаются
            регионам грантом.
          </li>
          <li>
            Надолго: налог до 12 % стабильность не снижает; если казну опустошают награды игрокам — значит, в регионе
            много боёв и заданий, это нормально, но казну придётся пополнять.
          </li>
        </UL>
      </Section>

      <Section id="recipe-merchant-cash">
        <H3>Торговцу нечем платить</H3>
        <UL>
          <li>
            Игрок видит «У меня сейчас нет на это денег» — касса торговца меньше суммы. Нажмите «Пополнить кассы
            торговцев» (вкладка «Торговцы»): касса дойдёт до нормы.
          </li>
          <li>
            Торговец пропущен с причиной «нет нормы» — у него нет рыночных товаров с «Нормой склада» больше 0.
            Задайте норму склада в лавке на странице НПС.
          </li>
          <li>Касса пополняется и сама — когда жители покупают у торговца. Бедный регион — бедные торговцы.</li>
        </UL>
      </Section>

      <Section id="recipe-bank-interest">
        <H3>Банк не платит проценты</H3>
        <UL>
          <li>Проверьте «Банк есть»: у выключенного банка проценты не начисляются.</li>
          <li>
            У банка нет свободных денег (свои деньги минус резерв 20 % от вкладов жителей). Добавьте «Капитал из
            казны» во вкладке «Банки».
          </li>
          <li>
            Ставки низкие, но не нулевые — значит, займов мало и банк снизил ставки вкладов (до 20 % от базовых).
            Это нормально и само выправится, когда займов станет больше.
          </li>
          <li>Вклады игроков при этом в безопасности: хранилище вкладов в займы не идёт.</li>
        </UL>
      </Section>

      <Section id="recipe-invariant">
        <H3>Сводка пишет «Расхождение»</H3>
        <P>
          Это не ошибка настройки, а признак того, что где-то деньги изменили в обход журнала (ошибка в коде или
          ручная правка базы). <B>Не исправляйте это эмиссией или корректировкой</B> — они записываются в журнал и
          расхождение не уберут. Перепишите из «Сводки», что не сошлось (сумма мира, аукцион, вклады, караваны в
          пути, список персонажей «баланс / по журналу»), и передайте разработчикам.
        </P>
      </Section>

      <Section id="recipe-prices">
        <H3>Цены растут или падают (инфляция и дефляция)</H3>
        <UL>
          <li>
            Цены в регионе зависят от <B>запаса</B> относительно нормы, а не напрямую от количества денег. Откройте
            редактор региона и посмотрите, у каких групп множитель далёк от ×1.
          </li>
          <li>
            <B>Растут</B> (запасы ниже нормы): регион производит меньше, чем потребляет, или жители стали богаче и
            покупают больше. Поднимите производство группы; не выпускайте лишних денег в кошельки.
          </li>
          <li>
            <B>Падают</B> (запасы выше нормы, товар портится): производство выше потребления или жителям не на что
            покупать. Снизьте производство или проверьте кошелёк и жалованье (см. «Пустая казна»).
          </li>
          <li>
            Денег у игроков становится больше от эмиссии (смотрите «Выпущено» в «Сводке») и от казн в минусе —
            регион, раздавший больше, чем собрал, по сути печатает деньги в долг.
          </li>
        </UL>
      </Section>

      <Section id="recipe-population-scale">
        <H3>Перешли на масштаб населения (регионы раздуты)</H3>
        <P>
          Если в регионах уже записано лорное население (120 к … 4.0 м), а пересчёт до этого шёл по полному числу
          жителей, кошельки, казны и запасы регионов накоплены в сто раз больше, чем нужно при масштабе 1 к 100.
          Приведите их к масштабу одной кнопкой:
        </P>
        <OL>
          <li>«{TAB_NAME.regions}» → «Заполнить регионы по шаблонам».</li>
          <li>
            Включите «Запасы — к норме» (нормы пересчитываются по расчётному населению), «Вернуть излишек кошелька
            жителей в эмиссию» и «Вернуть излишек казны в эмиссию». Учтите: из казны уходит всё выше резерва
            жалованья, включая деньги, пришедшие от игроков.
          </li>
          <li>
            Впишите комментарий и нажмите «Заполнить». Вклады и займы жителей в банке сначала приводятся к масштабу
            (вклады игроков не трогаются), затем кошельки и казны встают ровно на стартовый уровень, лишнее
            вернётся в эмиссию («Выпущено» в «Сводке» уменьшится). Повторное нажатие ничего не двигает.
          </li>
        </OL>
      </Section>

      <Section id="recipe-events">
        <H3>Событий слишком много, мало или нет</H3>
        <UL>
          <li>
            <B>Нет совсем.</B> Проверьте во вкладке «{TAB_NAME.tick}»: включён ли автопересчёт по расписанию (события
            бросаются только в плановых пересчётах, «Пересчитать сейчас» их не бросает) и стоит ли 1 в
            «Автоматические события». Регион должен участвовать в пересчёте (шаблон и население больше 0).
          </li>
          <li>
            <B>Событие не выпадает в регионе.</B> Откройте его шаблон во вкладке «{TAB_NAME.events}»: включено ли
            оно, способ запуска «Случайно», вес больше 0, отмечен ли шаблон этого региона (или ничего — значит, любой) и
            подходит ли сезон. Если сезоны отмечены, а календарь игры был недоступен, такое событие в этот пересчёт
            пропускается.
          </li>
          <li>
            <B>Слишком часто или редко.</B> Параметр «Частота» — среднее число случайных событий на регион за сезон:
            0,5 — вдвое реже, 2 — вдвое чаще. Помните, что сверху добавляются цепочки, распространение и бунты; их
            шансы — в шаблонах событий («Шанс перекинуться», «Цепочки») и «Глубина распространения» в «Пересчёте».
          </li>
          <li>
            <B>Беды наслаиваются и регион не выбирается из кризиса.</B> Уменьшите «Предел событий в регионе» (новые
            события не придут, пока идут старые) или поднимите «Минимальный общий множитель». Идущее событие можно
            отменить во вкладке «{TAB_NAME.events}» → «Активные».
          </li>
          <li>
            <B>Бунты один за другим.</B> Бунт — следствие низкой стабильности: сначала лечите причину (голод, налог,
            пустая казна — см. рецепты выше). Временно можно увеличить «Бунт через, дней» или опустить «Порог бунта».
          </li>
          <li>
            Нужна полная тишина (например, на время отладки)? Поставьте 0 в «Автоматические события»: идущие события
            доживут до конца, ручной запуск продолжит работать.
          </li>
        </UL>
      </Section>

      <Section id="recipe-mint">
        <H3>Монетный двор не чеканит или съедает весь лимит</H3>
        <UL>
          <li>
            <B>Двор закрыт.</B> Во вкладке «{TAB_NAME.mint}» у карточки страны написана причина: нет столицы (выберите
            её вручную), столица не в пересчёте, двор выключен, лимит 0 или в столице нет запаса «Руда и металл».
          </li>
          <li>
            <B>Двор сам не чеканит.</B> Запас «Руда и металл» столицы не выше порога. Опустите «Порог двора» или
            дождитесь руды от игроков.
          </li>
          <li>
            <B>Монетчик не открывается.</B> НПС должен иметь роль «Монетчик», быть живым и стоять в локации столицы;
            руда должна быть в списке руды с включённым приёмом.
          </li>
          <li>
            <B>Двор выбирает лимит сам, игрокам не остаётся.</B> Поднимите «Порог двора» (например, до 150 %), снизьте
            «Курс двора» или задайте лимит с запасом. Лимит общий и обнуляется только с новым сезоном.
          </li>
          <li>
            <B>Квота не пришла.</B> Квота выдаётся один раз за сезон, в ближайшем пересчёте, где её сумма больше 0
            (задали сумму посреди сезона — придёт в следующем пересчёте). Если в этом сезоне квота уже выдана, новая
            сумма заработает только со следующего сезона. Регион получает долю, только если участвует в пересчёте и его деньги (жители + казна) ниже нормы; если ниже нормы никого нет, квота ждёт.
          </li>
        </UL>
      </Section>

      <Section id="recipe-caravans">
        <H3>Как открыть торговлю между двумя странами</H3>
        <OL>
          <li>
            Откройте вкладку «{TAB_NAME.caravans}» → «Торговля между странами». Найдите пару поиском по названию
            страны (пара одна на обе стороны: «А ↔ Б» — то же, что «Б ↔ А»).
          </li>
          <li>
            Поставьте галочку «торгуют» и впишите пошлину в процентах (0–100, по умолчанию 10). Пошлину платят жители
            страны-покупателя сверх цены, она идёт в казну их страны.
          </li>
          <li>
            Нажмите «Сохранить». Первые караваны между странами отправятся в ближайшем пересчёте (можно «Пересчитать
            сейчас») и приедут через 2 пересчёта. Новая пошлина действует на новые караваны.
          </li>
        </OL>
        <H3>Караваны не ходят</H3>
        <UL>
          <li>
            Проверьте, что «Караваны» включены (параметры во вкладке «{TAB_NAME.caravans}»), а оба региона участвуют
            в пересчёте (шаблон и население больше 0) и уже пересчитывались хотя бы раз.
          </li>
          <li>
            Нужна разница: у продавца запас выше нормы, у покупателя — ниже (с учётом уже едущих караванов). Если у
            всех регионов запас около нормы, возить нечего — это нормально.
          </li>
          <li>
            У покупателя пустой кошелёк жителей (а для еды — ещё и казна в нуле или в минусе) — платить нечем.
            Пополните кошелёк или казну (см. «Пустая казна»).
          </li>
          <li>
            Сделка дешевле «Минимальной сделки» не отправляется; у продавца идёт «Набег» или «Бунт» — он не вывозит.
          </li>
          <li>Между странами — открыта ли торговля для этой пары. Внутри страны разрешения не нужно.</li>
        </UL>
      </Section>

      <Section id="recipe-guild">
        <H3>Как открыть гильдию в регионе</H3>
        <OL>
          <li>Регион должен участвовать в пересчёте (шаблон и население больше 0).</li>
          <li>
            На странице НПС создайте или выберите НПС, задайте роль «Гильдия торговцев» и поставьте его в локацию
            этого региона.
          </li>
          <li>
            Проверьте во вкладке «{TAB_NAME.guild}» → «Регионы», что у региона есть живой представитель и бюджет
            больше 0 (он появляется после первого пересчёта).
          </li>
          <li>
            Нажмите «Пересчитать сейчас» во вкладке «{TAB_NAME.tick}» — регион выставит заказы на группы, которых не
            хватает. Они появятся в списке заказов и в карточке региона.
          </li>
        </OL>
        <H3>Заказов нет или их не сдать</H3>
        <UL>
          <li>Запас всех групп выше порога — нехватки нет, это нормально.</li>
          <li>
            Кошелёк жителей пуст (для еды — и казна в нуле или в минусе): заказы закрываются «нет денег». Пополните
            кошелёк или казну (см. «Пустая казна»).
          </li>
          <li>Заказы выключены в параметрах вкладки «{TAB_NAME.guild}».</li>
          <li>
            Игрок видит «торговцы региона продают его слишком дёшево» — цена предмета упёрлась в цену торговца;
            это защита от перепродажи.
          </li>
        </UL>
      </Section>

      <Section id="recipe-classes">
        <H3>Регион копит деньги или беднеет</H3>
        <UL>
          <li>
            <B>Деньги жителей намного выше нормы</B> («{TAB_NAME.regions}» — больше 100 % нормы). Это нормально после
            притока денег от игроков: налог с накоплений и сдвиг классов вверх постепенно поглотят излишек. Быстрее —
            поднимите «Налог с накоплений» или «Вес денег относительно нормы».
          </li>
          <li>
            <B>Деньги ниже нормы, регион беднеет.</B> Проверьте голод и цены (бедные первыми бросают покупки). Помогут
            квота сезона (идёт только регионам ниже нормы), «Дотация по нехватке», снижение налога или «Заполнить
            регионы» с пополнением кошельков.
          </li>
          <li>
            <B>Доли не двигаются.</B> Сигнал в мёртвой зоне — так и задумано для обычного региона. Нужны сдвиги
            быстрее — поднимите скорости подъёма и обеднения или уменьшите мёртвую зону.
          </li>
          <li>
            <B>Доли «убежали» от лора.</B> Поправьте доли в редакторе региона или нажмите «Применить шаблон» (он сбросит
            и товары).
          </li>
          <li>
            <B>Что-то пошло не так после включения.</B> «{TAB_NAME.tick}» → «Классы жителей (1 — да, 0 — нет)» = 0 —
            расчёт сразу возвращается к прежнему, доли сохраняются.
          </li>
        </UL>
      </Section>

      <p className="text-white/40 text-xs">
        Числа в гайде — значения по умолчанию; если вы меняли параметры во вкладке «{TAB_NAME.tick}», действуют ваши.
      </p>
    </div>
  );
};

export default EconomyGuide;
