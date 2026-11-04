import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  fetchRegionsSuspicion,
  fetchShadowCrimes,
  SHADOW_PAGE_SIZE,
  type RegionSuspicion,
  type ShadowCrime,
  type ShadowCrimeFilter,
} from '../../../api/shadowAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { formatServerDateTime } from '../../../utils/serverDate';
import RemainingText from '../../CommonComponents/RemainingText';
import CrimeActionModal, { type CrimeAction, type CrimeActionTarget } from './CrimeActionModal';
import {
  CRIME_STATUS_CLASSES,
  CRIME_TYPE_LABELS,
  SUSPICION_CLASSES,
  crimeStatusLabel,
  isOpenCrime,
  pct,
} from './shadowLabels';

interface UnresolvedCrimesTabProps {
  canManage: boolean;
}

const LABEL = 'text-white/50 text-xs font-medium uppercase tracking-[0.06em]';
const ID_RE = /^\d*$/;

const STATUS_OPTIONS: { value: ShadowCrimeFilter; label: string }[] = [
  { value: 'open', label: 'Нераскрытые (все)' },
  { value: 'unwitnessed', label: 'Не замечено' },
  { value: 'masked', label: 'В маске' },
  { value: 'reported', label: 'Замечено / раскрыто' },
  { value: 'closed', label: 'Закрыто' },
  { value: 'all', label: 'Все дела' },
];

const crimeTitle = (c: ShadowCrime): string =>
  `${CRIME_TYPE_LABELS[c.crime_type] ?? c.crime_type} · ${c.character_name ?? `персонаж #${c.character_id}`} · ` +
  `${c.region_name ?? `край #${c.region_id}`}`;

const Info = ({ name, children }: { name: string; children: React.ReactNode }) => (
  <div className="flex flex-col gap-0.5 min-w-0">
    <span className={LABEL}>{name}</span>
    <span className="text-white text-sm break-words">{children}</span>
  </div>
);

/** «Нераскрытые дела» (FEAT-199): deferred crimes with staff reveal / close + the regions' suspicion. */
const UnresolvedCrimesTab = ({ canManage }: UnresolvedCrimesTabProps) => {
  const [status, setStatus] = useState<ShadowCrimeFilter>('open');
  const [region, setRegion] = useState('');
  const [characterText, setCharacterText] = useState('');
  const [characterId, setCharacterId] = useState<number | null>(null);
  const [page, setPage] = useState(1);

  const [items, setItems] = useState<ShadowCrime[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  /** Regions seen in the suspicion list and in loaded pages — options of the region filter. */
  const [regionNames, setRegionNames] = useState<Record<number, string>>({});
  const [suspicion, setSuspicion] = useState<RegionSuspicion[] | null>(null);
  const [suspicionError, setSuspicionError] = useState<string | null>(null);

  const [target, setTarget] = useState<CrimeActionTarget | null>(null);
  const [action, setAction] = useState<CrimeAction>('reveal');

  const rememberRegions = (list: { region_id: number; region_name: string | null }[]) => {
    setRegionNames((prev) => {
      const next = { ...prev };
      list.forEach((r) => {
        next[r.region_id] = r.region_name ?? `Край #${r.region_id}`;
      });
      return next;
    });
  };

  const load = useCallback(() => {
    setLoading(true);
    fetchShadowCrimes({ status, region_id: region ? Number(region) : null, character_id: characterId, page })
      .then((d) => {
        setItems(d.items);
        setTotal(d.total);
        setLoadError(null);
        rememberRegions(d.items);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить дела');
        setLoadError(msg);
        toast.error(msg);
      })
      .finally(() => setLoading(false));
  }, [status, region, characterId, page]);

  useEffect(load, [load]);

  const loadSuspicion = useCallback(() => {
    fetchRegionsSuspicion()
      .then((list) => {
        setSuspicion(list);
        setSuspicionError(null);
        rememberRegions(list);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить подозрение краёв');
        setSuspicionError(msg);
        toast.error(msg);
      });
  }, []);

  useEffect(loadSuspicion, [loadSuspicion]);

  const applyCharacter = () => {
    const v = characterText.trim();
    setCharacterId(v ? Number(v) : null);
    setPage(1);
  };

  const openAction = (c: ShadowCrime, a: CrimeAction) => {
    setAction(a);
    setTarget({ id: c.id, title: crimeTitle(c) });
  };

  const onDone = () => {
    load();
    loadSuspicion();
  };

  const pages = Math.max(1, Math.ceil(total / SHADOW_PAGE_SIZE));
  const regionOptions = Object.entries(regionNames).sort((a, b) => a[1].localeCompare(b[1], 'ru'));

  return (
    <div className="flex flex-col gap-5">
      {/* Region suspicion */}
      <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-3 min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Подозрение краёв</h2>
          <button type="button" className="btn-line !w-auto !px-4 !py-1 !text-sm" onClick={loadSuspicion}>
            Обновить
          </button>
        </div>
        <p className="text-white/50 text-sm">Игроки видят только текст состояния на карточке края; числа — только здесь.</p>
        {suspicionError && !suspicion && <p className="text-site-red text-sm">{suspicionError}</p>}
        {suspicion && suspicion.length === 0 && <p className="text-white/50 text-sm">Во всех краях спокойно</p>}
        {suspicion && suspicion.length > 0 && (
          <div className="flex flex-col divide-y divide-white/[0.06]">
            {suspicion.map((s) => (
              <div key={s.region_id} className="grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,2fr)] gap-x-3 gap-y-1 py-2 items-center">
                <span className="text-white text-sm truncate">{s.region_name ?? `Край #${s.region_id}`}</span>
                <span className="text-white text-base font-medium text-right sm:text-left">{s.value}</span>
                <span className={`text-sm col-span-2 sm:col-span-1 ${SUSPICION_CLASSES[s.code] ?? 'text-white/70'}`}>{s.label}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Crimes */}
      <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Дела</h2>
          <button type="button" className="btn-line !w-auto !px-4 !py-1 !text-sm disabled:opacity-40" disabled={loading}
            onClick={load}>
            Обновить
          </button>
        </div>
        <p className="text-white/50 text-sm">
          Преступления, которые никто не заметил или совершённые в маске. Каждые сутки по делу бросается шанс раскрытия;
          после срока дело закрывается само.
          {!canManage && ' Раскрывать и закрывать дела можно с правом reputation:manage.'}
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <label className="flex flex-col gap-1 min-w-0">
            <span className={LABEL}>Статус</span>
            <select className="input-underline w-full" value={status}
              onChange={(e) => {
                setStatus(e.target.value as ShadowCrimeFilter);
                setPage(1);
              }}>
              {STATUS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value} className="bg-site-dark text-white">{o.label}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 min-w-0">
            <span className={LABEL}>Край</span>
            <select className="input-underline w-full" value={region}
              onChange={(e) => {
                setRegion(e.target.value);
                setPage(1);
              }}>
              <option value="" className="bg-site-dark text-white">Все края</option>
              {regionOptions.map(([id, name]) => (
                <option key={id} value={id} className="bg-site-dark text-white">{name}</option>
              ))}
            </select>
          </label>
          <form className="flex flex-col gap-1 min-w-0" onSubmit={(e) => {
            e.preventDefault();
            applyCharacter();
          }}>
            <span className={LABEL}>ID персонажа</span>
            <div className="flex gap-2 items-end">
              <input className="input-underline w-full" inputMode="numeric" value={characterText} placeholder="любой"
                onChange={(e) => {
                  if (ID_RE.test(e.target.value)) setCharacterText(e.target.value);
                }}
                onBlur={applyCharacter} />
            </div>
          </form>
        </div>

        {loadError && items.length === 0 && <p className="text-site-red text-sm">{loadError}</p>}
        {loading && items.length === 0 && !loadError && (
          <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        )}
        {!loading && !loadError && items.length === 0 && <p className="text-white/50 text-sm">Дел не найдено</p>}

        <div className="flex flex-col gap-2">
          {items.map((c) => {
            const open = isOpenCrime(c.status);
            return (
              <div key={c.id} className="flex flex-col gap-3 rounded-card border border-white/[0.07] bg-white/[0.02] p-3 sm:p-4 min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 min-w-0">
                  <span className="text-white/40 text-xs">#{c.id} · {formatServerDateTime(c.created_at)}</span>
                  <span className="text-white text-sm font-medium">{CRIME_TYPE_LABELS[c.crime_type] ?? c.crime_type}</span>
                  <span className={`text-xs uppercase tracking-[0.06em] ${CRIME_STATUS_CLASSES[c.status] ?? 'text-white/60'}`}>
                    {crimeStatusLabel(c.status, c.revealed_at)}
                  </span>
                  {c.masked && <span className="text-xs text-white/60">маска</span>}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                  <Info name="Персонаж">
                    <Link to={`/admin/characters/${c.character_id}`} className="site-link">
                      {c.character_name ?? `#${c.character_id}`}
                    </Link>
                  </Info>
                  <Info name="Жертва">{c.victim_name ?? (c.victim_id ? `#${c.victim_id}` : '—')}</Info>
                  <Info name="Край / локация">
                    {c.region_name ?? `#${c.region_id}`}
                    {(c.location_name || c.location_id) && ` · ${c.location_name ?? `#${c.location_id}`}`}
                  </Info>
                  <Info name="Свидетели">
                    шанс {pct(c.witness_chance_pct)}
                    {c.witness_roll_pct != null && `, бросок ${pct(c.witness_roll_pct)}`}
                  </Info>
                  <Info name="Последствия">
                    репутация {c.reputation_delta ?? '—'} · розыск +{c.wanted_points}
                    {c.wanted_floor != null && ` (не меньше ${c.wanted_floor})`}
                  </Info>
                  <Info name="Попыток раскрытия">{c.reveal_attempts}</Info>
                  {open ? (
                    <>
                      <Info name="Следующий бросок">
                        {c.next_roll_at
                          ? <RemainingText until={c.next_roll_at} prefix="через" doneText="при следующем проходе" className="text-gold" />
                          : '—'}
                      </Info>
                      <Info name="Закроется">
                        {c.reveal_until
                          ? <RemainingText until={c.reveal_until} prefix="через" doneText="срок истёк" className="text-gold" />
                          : '—'}
                      </Info>
                    </>
                  ) : (
                    <Info name={c.revealed_at ? 'Раскрыто' : 'Решено'}>
                      {c.revealed_at ? formatServerDateTime(c.revealed_at) : c.resolved_at ? formatServerDateTime(c.resolved_at) : '—'}
                    </Info>
                  )}
                </div>
                {canManage && open && (
                  <div className="flex flex-col sm:flex-row gap-2">
                    <button type="button" className="btn-blue w-full sm:w-auto !px-6" onClick={() => openAction(c, 'reveal')}>
                      Раскрыть
                    </button>
                    <button type="button" className="btn-line w-full sm:w-auto !px-6" onClick={() => openAction(c, 'close')}>
                      Закрыть дело
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {total > SHADOW_PAGE_SIZE && (
          <div className="flex flex-wrap items-center justify-center gap-3">
            <button type="button" className="btn-line !w-auto !px-4 !py-1 !text-sm disabled:opacity-40"
              disabled={loading || page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              Назад
            </button>
            <span className="text-white/60 text-sm">Стр. {page} из {pages} · всего {total}</span>
            <button type="button" className="btn-line !w-auto !px-4 !py-1 !text-sm disabled:opacity-40"
              disabled={loading || page >= pages} onClick={() => setPage((p) => Math.min(pages, p + 1))}>
              Вперёд
            </button>
          </div>
        )}
      </section>

      <CrimeActionModal target={target} action={action} onClose={() => setTarget(null)} onDone={onDone} />
    </div>
  );
};

export default UnresolvedCrimesTab;
