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
import { formatDateTime, formatPercent } from './economyLabels';
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
  { from: ['treasury', 'Казна страны'], to: ['treasury', 'Казна региона'], what: 'грант: 25 % денег страны делится между её регионами по числу жителей' },
  { from: ['treasury', 'Казна региона'], to: ['people', 'Кошелёк жителей'], what: 'жалованье' },
  { from: ['people', 'Кошелёк жителей'], to: ['business', 'Касса торговца'], what: 'жители покупают у живых торговцев' },
  { from: ['business', 'Касса торговца'], to: ['treasury', 'Казна региона'], what: 'налог с выручки торговца' },
  { from: ['business', 'Касса торговца'], to: ['people', 'Кошелёк жителей'], what: 'торговец докупает товар у региона и отдаёт излишек кассы' },
  { from: ['people', 'Кошелёк жителей'], to: ['business', 'Банк'], what: 'вклады жителей и погашение их займов (обратно — займы и проценты)' },
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
  const [data, setData] = useState<GuideData>({
    settings: EMPTY,
    regions: EMPTY,
    templates: EMPTY,
    goods: EMPTY,
    items: EMPTY,
    merchants: EMPTY,
    banks: EMPTY,
    sim: EMPTY,
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
    ])
      .then(([settings, regions, templates, goods, items, merchants, banks, sim]) => {
        setData({
          settings: settle(settings, 'Не удалось загрузить настройки валюты'),
          regions: settle(regions, 'Не удалось загрузить регионы'),
          templates: settle(templates, 'Не удалось загрузить шаблоны'),
          goods: settle(goods, 'Не удалось загрузить группы товаров'),
          items: settle(items, 'Не удалось загрузить группы предметов'),
          merchants: settle(merchants, 'Не удалось загрузить торговцев'),
          banks: settle(banks, 'Не удалось загрузить банки'),
          sim: settle(sim, 'Не удалось загрузить пересчёт'),
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
    if (bigWithoutBank > 0) lines.push(`Столиц и портов в пересчёте без банка: ${bigWithoutBank}`);
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

  const invariantStatus: StepStatus = summary
    ? summary.invariant.ok
      ? { tone: 'done', lines: ['Сводка: «Сходится»', `Выпущено всего: ${format(summary.totals.issued, true)}`] }
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
          шаблонов: Столица (25 000 жителей, налог 12 %), Портовый (12 000, 10 %), Шахтёрский (6 000, 10 %), Аграрный
          (8 000, 8 %), Лесной (4 000, 8 %), Магический (7 000, 12 %), Пограничная крепость (3 000, 6 %), Сельская
          округа (2 500, 6 %). Назначьте шаблон каждому региону, который должен «жить»: «Регионы» → регион → поле
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
          кошелёк жителей — до 7 дней их потребностей по базовым ценам, казну — до резерва жалованья (7 дней налогов).
          Галочка «Население из шаблона» (по умолчанию выключена) ставит население шаблона регионам, где оно 0 —
          без неё такие регионы пропускаются. Галочка «Открыть банки в столицах и портах» сразу включает банк
          регионам с шаблоном «Столица» или «Портовый» и берёт ему стартовый капитал из казны. Повторное нажатие
          доливает только недостающее. Нужны права
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
          {format(20000, true)}, но не больше, чем в казне). Игроки пользуются банком через НПС с ролью «Банкир» —
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
          хранилище аукциона и вклады игроков совпадают со своими записями. «Выпущено» — сколько денег создано
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
            регионов (эмиссия не облагается) и каждые 6 часов раздаёт 25 % своих денег регионам как грант, пропорционально числу жителей.
          </li>
          <li>
            <B>Казна Скитальцев</B> — общая казна мира: платит награды боевого пропуска, получает платежи в
            локациях без региона.
          </li>
          <li>
            <B>Кошелёк жителей</B> — общие деньги всех жителей региона (жители — не персонажи, а число «население»).
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
            <B>Производство.</B> Каждая группа производит «производство на 1000 жителей» × население. Меньше —
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
          «Пересчитать сейчас» делает ещё один такой же шаг немедленно. Подсказки к каждому параметру — во
          вкладке «Пересчёт».
        </P>
      </Section>

      <Section id="regions">
        <H3>Жители, товары и цены</H3>
        <UL>
          <li>
            <B>Норма запаса</B> группы = дни запаса группы × (потребление жителей в день + сырьё для производства в
            день). Пример: продовольствие — 300 единиц на 1000 жителей в день, запас на 7 дней; в Столице на 25 000
            жителей это 7 500 единиц в день и норма 52 500.
          </li>
          <li>
            <B>Стартовый кошелёк</B> при заполнении — 7 дней потребностей по базовым ценам. Только еда Столицы стоит
            7 500 × {format(2, true)} = {format(15000, true)} в день.
          </li>
          <li>
            <B>Производство шаблона</B>: больше 1 — специализация (Шахтёрский: руда ×2), меньше 1 — хроническая
            нехватка (Пограничная крепость: еда ×0,85). Нехватку регион компенсирует ценой: дорогой товар меньше
            покупают и больше производят.
          </li>
          <li>
            Игрок видит у региона только слова («Город сыт», «Цены высокие», «Казна в порядке»), без чисел.
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
            Пограничной крепости своей еды не хватает специально.
          </li>
          <li>
            <B>Еда есть, но жителям не на что купить</B> (кошелёк меньше дня потребностей): «Заполнить регионы по
            шаблонам» доведёт кошелёк до 7 дней; проверьте казну — если она ниже резерва, жалованье урезано (см.
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
          расхождение не уберут. Перепишите из «Сводки», что не сошлось (сумма мира, аукцион, вклады, список
          персонажей «баланс / по журналу»), и передайте разработчикам.
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

      <p className="text-white/40 text-xs">
        Числа в гайде — значения по умолчанию; если вы меняли параметры во вкладке «{TAB_NAME.tick}», действуют ваши.
      </p>
    </div>
  );
};

export default EconomyGuide;
