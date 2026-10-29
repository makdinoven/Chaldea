import { useCallback, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { ChevronRight, RefreshCw } from 'lucide-react';
import { fetchEconomyRegions, postEconomyRegionsFill } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { useCurrency } from '../../../hooks/useCurrency';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import type { EconFillResult, EconRegionItem } from '../../../types/economy';
import RegionEconomyEditor from './RegionEconomyEditor';
import { formatDateTime } from './economyLabels';
import { HungerBadge, ScaleBar } from './regionBits';

const COMMENT_MIN = 3;
const COMMENT_MAX = 500;

interface EconomyRegionsProps {
  canSettings: boolean;
  canEmit: boolean;
  /** Called after anything that moves money (fill) — the summary is refreshed. */
  onMoneyChanged: () => void;
}

const balanceClass = (n: number) => (n < 0 ? 'text-site-red' : 'text-white');

interface FillDialogProps {
  templatedCount: number;
  onClose: () => void;
  onDone: (result: EconFillResult) => void;
}

/** «Заполнить регионы по шаблонам»: goods and stocks from templates + one emission into the purses. */
const FillDialog = ({ templatedCount, onClose, onDone }: FillDialogProps) => {
  const [populationFromTemplate, setPopulationFromTemplate] = useState(false);
  const [resetStocks, setResetStocks] = useState(true);
  const [fundPurses, setFundPurses] = useState(true);
  const [treasuryToReserve, setTreasuryToReserve] = useState(true);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);

  const trimmed = comment.trim();
  const commentValid = trimmed.length >= COMMENT_MIN && trimmed.length <= COMMENT_MAX;

  const submit = async () => {
    setBusy(true);
    try {
      const result = await postEconomyRegionsFill({
        population_from_template: populationFromTemplate,
        reset_stocks: resetStocks,
        fund_purses: fundPurses,
        treasury_to_reserve: treasuryToReserve,
        comment: trimmed,
      });
      onDone(result);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось заполнить регионы по шаблонам'));
    } finally {
      setBusy(false);
    }
  };

  const options: { id: string; checked: boolean; set: (v: boolean) => void; label: string; hint: string }[] = [
    {
      id: 'econ-fill-population',
      checked: populationFromTemplate,
      set: setPopulationFromTemplate,
      label: 'Население из шаблона',
      hint: 'Только для регионов, где население ещё не задано (0).',
    },
    {
      id: 'econ-fill-stocks',
      checked: resetStocks,
      set: setResetStocks,
      label: 'Запасы — к норме',
      hint: 'Товары и нормы копируются из шаблона, запасы выставляются в норму.',
    },
    {
      id: 'econ-fill-purses',
      checked: fundPurses,
      set: setFundPurses,
      label: 'Деньги жителям (эмиссия)',
      hint: 'Кошельки жителей пополняются до стартового запаса. Повторное нажатие не добавит лишнего.',
    },
    {
      id: 'econ-fill-treasury',
      checked: treasuryToReserve,
      set: setTreasuryToReserve,
      label: 'Пополнить казну до резерва жалованья',
      hint: 'Без резерва жалованье жителям начнётся только через ~неделю, пока казна не наберётся из налогов.',
    },
  ];

  return (
    <ModalShell
      open
      onClose={onClose}
      dismissible={!busy}
      title="Заполнить регионы по шаблонам"
      size="md"
      footer={
        <>
          <button type="button" className="btn-line w-full sm:w-auto !text-xs !py-2 !px-5" onClick={onClose} disabled={busy}>
            Отмена
          </button>
          <button
            type="button"
            className="btn-blue w-full sm:w-auto !py-2 !px-5 !text-xs"
            disabled={!commentValid || busy}
            onClick={submit}
          >
            {busy ? 'Заполнение...' : 'Заполнить'}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <p className="text-white/80 text-sm">
          Будут заполнены все регионы с шаблоном: {templatedCount}. Регионы без шаблона не затрагиваются.
        </p>
        {options.map((o) => (
          <label key={o.id} htmlFor={o.id} className="flex items-start gap-3 cursor-pointer select-none">
            <input
              id={o.id}
              type="checkbox"
              checked={o.checked}
              onChange={(e) => o.set(e.target.checked)}
              className="w-4 h-4 mt-0.5 shrink-0 accent-gold"
            />
            <span className="flex flex-col gap-0.5">
              <span className="text-white text-sm">{o.label}</span>
              <span className="text-white/40 text-xs">{o.hint}</span>
            </span>
          </label>
        ))}
        <div className="flex flex-col gap-1">
          <label htmlFor="econ-fill-comment" className="text-white/60 text-xs uppercase tracking-[0.06em]">
            Комментарий (обязательно)
          </label>
          <textarea
            id="econ-fill-comment"
            className="textarea-bordered w-full"
            rows={3}
            maxLength={COMMENT_MAX}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Причина: попадёт в журнал операций"
          />
          {comment !== '' && !commentValid && (
            <p className="text-site-red text-xs">От {COMMENT_MIN} до {COMMENT_MAX} символов</p>
          )}
        </div>
      </div>
    </ModalShell>
  );
};

/** «Регионы» (FEAT-182): every region with its economy numbers; drill-down into the region editor. */
const EconomyRegions = ({ canSettings, canEmit, onMoneyChanged }: EconomyRegionsProps) => {
  const { format } = useCurrency();
  const [regions, setRegions] = useState<EconRegionItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [onlySimulated, setOnlySimulated] = useState(false);
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [fillOpen, setFillOpen] = useState(false);
  const [fillResult, setFillResult] = useState<EconFillResult | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    fetchEconomyRegions()
      .then((items) => {
        setRegions(items);
        setError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить экономику регионов');
        setError(msg);
        toast.error(msg);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const visible = useMemo(() => {
    const q = query.trim().toLocaleLowerCase('ru');
    return (regions ?? [])
      .filter((r) => !onlySimulated || r.simulated)
      .filter(
        (r) =>
          !q ||
          (r.name ?? '').toLocaleLowerCase('ru').includes(q) ||
          (r.country_name ?? '').toLocaleLowerCase('ru').includes(q),
      )
      .sort(
        (a, b) =>
          (a.country_name ?? '').localeCompare(b.country_name ?? '', 'ru') ||
          (a.name ?? '').localeCompare(b.name ?? '', 'ru'),
      );
  }, [regions, onlySimulated, query]);

  const templatedCount = (regions ?? []).filter((r) => r.template_code).length;
  const simulatedCount = (regions ?? []).filter((r) => r.simulated).length;
  const canFill = canSettings && canEmit;

  if (selectedId !== null) {
    return (
      <RegionEconomyEditor
        regionId={selectedId}
        canEdit={canSettings}
        onBack={() => {
          setSelectedId(null);
          load();
        }}
        onChanged={load}
      />
    );
  }

  const regionTitle = (r: EconRegionItem) => r.name ?? `Регион #${r.region_id}`;
  const regionLabel = (id: number) => {
    const r = (regions ?? []).find((x) => x.region_id === id);
    return r ? regionTitle(r) : `Регион #${id}`;
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col lg:flex-row lg:items-end gap-4">
        <div className="flex flex-col gap-1 min-w-0 lg:w-72">
          <label htmlFor="econ-regions-q" className="text-white/60 text-xs uppercase tracking-[0.06em]">
            Поиск
          </label>
          <input
            id="econ-regions-q"
            type="text"
            className="input-underline w-full"
            placeholder="Регион или страна..."
            value={query}
            maxLength={100}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <label className="flex items-center gap-2 py-2 text-sm text-white/70 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={onlySimulated}
            onChange={(e) => setOnlySimulated(e.target.checked)}
            className="w-4 h-4 shrink-0 accent-gold"
          />
          Только в симуляции
        </label>
        <div className="flex flex-wrap items-center gap-3 lg:ml-auto">
          <span className="text-white/50 text-sm">
            В симуляции: {simulatedCount} из {regions?.length ?? 0}
          </span>
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-site-blue transition-colors duration-200 ease-site disabled:opacity-40"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Обновить
          </button>
          {canFill && (
            <button
              type="button"
              className="btn-blue w-full sm:w-auto !py-2 !px-5 !text-xs"
              disabled={templatedCount === 0}
              title={templatedCount === 0 ? 'Сначала назначьте шаблон хотя бы одному региону' : undefined}
              onClick={() => setFillOpen(true)}
            >
              Заполнить регионы по шаблонам
            </button>
          )}
        </div>
      </div>

      {fillResult && (
        <p className="text-sm text-white/80 rounded-card border border-stat-energy/30 bg-stat-energy/[0.06] px-4 py-3">
          Заполнено регионов: {fillResult.regions}. Выпущено жителям: {format(fillResult.emitted_purses)}, в казны:{' '}
          {format(fillResult.emitted_treasuries)}
          {fillResult.operation_ids.length > 0 && (
            <span className="text-white/50"> (операций: {fillResult.operation_ids.length})</span>
          )}
          {fillResult.skipped_no_population.length > 0 && (
            <span className="block text-white/50 mt-1">
              Без денег из-за нулевого населения: {fillResult.skipped_no_population.map(regionLabel).join(', ')}
            </span>
          )}
        </p>
      )}

      {error && !regions && <p className="text-site-red text-sm">{error}</p>}
      {!regions && !error && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
      {regions && visible.length === 0 && <p className="text-white/40 text-sm italic">Регионов не найдено.</p>}

      {regions && visible.length > 0 && (
        <div className={`transition-opacity ${loading ? 'opacity-60' : ''}`}>
          {/* Table — lg and up */}
          <div className="hidden lg:block bg-site-bg rounded-card border border-white/[0.07] px-4 py-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-white/50 text-xs uppercase tracking-[0.06em] text-left border-b border-white/10">
                  <th className="py-2 pr-3 font-normal">Регион</th>
                  <th className="py-2 pr-3 font-normal">Шаблон</th>
                  <th className="py-2 pr-3 font-normal text-right">Население</th>
                  <th className="py-2 pr-3 font-normal">Стабильность</th>
                  <th className="py-2 pr-3 font-normal">Достаток</th>
                  <th className="py-2 pr-3 font-normal">Еда</th>
                  <th className="py-2 pr-3 font-normal text-right">Жители</th>
                  <th className="py-2 pr-3 font-normal text-right">Казна</th>
                  <th className="py-2 font-normal">Пересчёт</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((r) => (
                  <tr
                    key={r.region_id}
                    onClick={() => setSelectedId(r.region_id)}
                    className="border-b border-white/[0.07] last:border-b-0 cursor-pointer hover:bg-white/[0.04] transition-colors duration-200 ease-site"
                  >
                    <td className="py-2 pr-3">
                      <span className="block text-white break-words">{regionTitle(r)}</span>
                      <span className="block text-white/40 text-xs">{r.country_name ?? 'Без страны'}</span>
                    </td>
                    <td className="py-2 pr-3 text-white/80">{r.template_name ?? <span className="text-white/30">—</span>}</td>
                    <td className="py-2 pr-3 text-right text-white/80">{r.population.toLocaleString('ru-RU')}</td>
                    <td className="py-2 pr-3">
                      {r.simulated ? <ScaleBar value={r.stability} tone="stability" label="Стабильность" /> : <span className="text-white/30">—</span>}
                    </td>
                    <td className="py-2 pr-3">
                      {r.simulated ? <ScaleBar value={r.prosperity} tone="prosperity" label="Достаток" /> : <span className="text-white/30">—</span>}
                    </td>
                    <td className="py-2 pr-3">
                      <HungerBadge hunger={r.hunger} simulated={r.simulated} />
                    </td>
                    <td className="py-2 pr-3 text-right whitespace-nowrap text-white/80">{format(r.purse)}</td>
                    <td className={`py-2 pr-3 text-right whitespace-nowrap ${balanceClass(r.treasury)}`}>{format(r.treasury)}</td>
                    <td className="py-2 text-white/50 text-xs whitespace-nowrap">
                      {r.last_tick_at ? formatDateTime(r.last_tick_at) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Cards — below lg */}
          <ul className="lg:hidden grid grid-cols-1 md:grid-cols-2 gap-3">
            {visible.map((r) => (
              <li key={r.region_id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(r.region_id)}
                  className="w-full text-left bg-site-bg rounded-card border border-white/[0.07] p-3 flex flex-col gap-2 hover:border-gold/40 transition-colors duration-200 ease-site"
                >
                  <span className="flex items-start gap-2">
                    <span className="flex-1 min-w-0">
                      <span className="block text-white text-sm font-medium break-words">{regionTitle(r)}</span>
                      <span className="block text-white/40 text-xs break-words">
                        {r.country_name ?? 'Без страны'} · {r.template_name ?? 'без шаблона'}
                        {r.population > 0 && ` · ${r.population.toLocaleString('ru-RU')} жит.`}
                      </span>
                    </span>
                    <ChevronRight size={16} className="text-gold shrink-0 mt-0.5" />
                  </span>
                  {r.simulated && (
                    <span className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-white/50">
                      <span>Стабильность</span>
                      <span>Достаток</span>
                      <ScaleBar value={r.stability} tone="stability" label="Стабильность" />
                      <ScaleBar value={r.prosperity} tone="prosperity" label="Достаток" />
                    </span>
                  )}
                  <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                    <HungerBadge hunger={r.hunger} simulated={r.simulated} />
                    <span className="text-white/50">
                      жители <span className="text-white/80">{format(r.purse)}</span>
                    </span>
                    <span className="text-white/50">
                      казна <span className={balanceClass(r.treasury)}>{format(r.treasury)}</span>
                    </span>
                  </span>
                  {r.last_tick_at && (
                    <span className="text-white/40 text-xs">Пересчёт: {formatDateTime(r.last_tick_at)}</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {fillOpen && (
        <FillDialog
          templatedCount={templatedCount}
          onClose={() => setFillOpen(false)}
          onDone={(result) => {
            setFillOpen(false);
            setFillResult(result);
            toast.success(
              `Регионы заполнены: ${result.regions}. Жителям: ${format(result.emitted_purses)}, в казны: ${format(result.emitted_treasuries)}`,
            );
            load();
            onMoneyChanged();
          }}
        />
      )}
    </div>
  );
};

export default EconomyRegions;
