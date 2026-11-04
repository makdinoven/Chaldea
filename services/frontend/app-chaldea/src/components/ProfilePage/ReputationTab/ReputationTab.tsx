// FEAT-197 — «Репутация» profile tab: tier + bar per visited region (grouped by country),
// the tier scale, and the paged journal. Private data; no numbers are ever shown.
// FEAT-198 — «Розыск» block: wanted level per region with its fine and jail term, plus the jail status.
// FEAT-199 — «Слава» (public tier + bar to the next tier) and «Слухи в подполье» (private infamy tier).
import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { ArrowDown, ArrowUp, BookOpen, EyeOff, Scale, Shield, Sparkles } from 'lucide-react';
import { fetchLawState, jailTermText, type LawStateOut, type LawWantedOut } from '../../../api/law';
import RemainingText from '../../CommonComponents/RemainingText';
import { fetchReputation, fetchReputationHistory } from '../../../api/reputation';
import { fetchRenown, type RenownView } from '../../../api/renown';
import type {
  ReputationHistoryItem,
  ReputationRegion,
  ReputationTierBrief,
} from '../../../api/reputation';
import { apiErrorMessage } from '../../../api/errors';
import { formatRelativeTime } from '../../../utils/serverDate';
import {
  REPUTATION_TONE_CHIP,
  REPUTATION_TONE_FILL,
  REPUTATION_TONE_TEXT,
  reputationTone,
} from '../../../utils/reputationTiers';
import PanelShell, { PANEL_DESKTOP_HEIGHT_CLASS } from '../PanelShell';
import EmptyState from '../shared/EmptyState';
import ErrorState from '../shared/ErrorState';
import LoadingState from '../shared/LoadingState';
import PanelCounter from '../shared/PanelCounter';
import ProfileCard from '../shared/ProfileCard';
import SectionHeader from '../shared/SectionHeader';

interface ReputationTabProps {
  characterId: number;
}

const HISTORY_PAGE_SIZE = 20;
const NO_COUNTRY_KEY = 'none';
const NO_COUNTRY_LABEL = 'Вне стран';
/** The neutral starting tier (fixed code; its name is editable by the admin). */
const START_TIER_CODE = 'wanderer';

const TAB_MOTION = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.3, ease: 'easeOut' as const },
};

interface CountryGroup {
  key: string;
  name: string;
  regions: ReputationRegion[];
}

const groupByCountry = (regions: ReputationRegion[]): CountryGroup[] => {
  const groups = new Map<string, CountryGroup>();
  regions.forEach((region) => {
    const key = region.country_id != null ? String(region.country_id) : NO_COUNTRY_KEY;
    const group = groups.get(key) ?? {
      key,
      name: region.country_name || NO_COUNTRY_LABEL,
      regions: [],
    };
    group.regions.push(region);
    groups.set(key, group);
  });
  return Array.from(groups.values());
};

/* ── Region row ── */

const RegionRow = ({ region }: { region: ReputationRegion }) => {
  const tone = reputationTone(region.tier_code);
  const percent = Math.round(Math.max(0, Math.min(1, region.progress)) * 100);
  return (
    <ProfileCard className="p-3 flex flex-col gap-2" variant={region.trade_refused ? 'danger' : 'default'}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 min-w-0">
        <span className="text-white text-sm font-medium break-words min-w-0">
          {region.region_name || 'Безымянный край'}
        </span>
        <span className={`text-sm font-medium ${REPUTATION_TONE_TEXT[tone]}`}>{region.tier_name}</span>
      </div>
      <div
        role="progressbar"
        aria-label={`Репутация: ${region.tier_name}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="stat-bar h-1.5 border-white/40"
      >
        <div className={`stat-bar-fill ${REPUTATION_TONE_FILL[tone]}`} style={{ width: `${percent}%` }} />
      </div>
      {region.trade_refused && (
        <p className="text-xs text-site-red">Торговцы этого края отказываются иметь с вами дело</p>
      )}
    </ProfileCard>
  );
};

/* ── Wanted (FEAT-198) ── */

const WantedRow = ({ wanted }: { wanted: LawWantedOut }) => (
  <ProfileCard className="p-3 flex flex-col gap-1" variant="danger">
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 min-w-0">
      <span className="text-white text-sm font-medium break-words min-w-0">
        {wanted.region_name || 'Безымянный край'}
      </span>
      <span className="text-sm font-medium text-site-red">{wanted.level_name}</span>
    </div>
    <p className="text-white/60 text-xs break-words">
      Штраф {wanted.fine.toLocaleString('ru-RU')} золота · срок {jailTermText(wanted.jail_hours)}
      {wanted.decaying ? ' · спадает со временем' : ''}
    </p>
  </ProfileCard>
);

const WantedSection = ({
  law,
  loading,
  error,
  onRetry,
}: {
  law: LawStateOut | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) => (
  <div className="flex flex-col gap-2">
    <SectionHeader title="Розыск" />
    {loading && !law ? (
      <p className="text-white/40 text-xs">Загрузка...</p>
    ) : error ? (
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-site-red text-xs">{error}</span>
        <button type="button" className="btn-line !text-xs !py-1 !px-3" onClick={onRetry}>
          Повторить
        </button>
      </div>
    ) : law ? (
      <>
        {law.jail && (
          <ProfileCard className="p-3 flex flex-col gap-1" variant="danger">
            <span className="text-white text-sm font-medium break-words">
              В тюрьме края «{law.jail.region_name || '—'}»
              {law.jail.location_name ? ` — «${law.jail.location_name}»` : ''}
            </span>
            <span className="text-white/60 text-xs">
              <RemainingText until={law.jail.until} doneText="срок истёк" className="text-gold-light" />
              {' · '}залог {law.jail.bail_price.toLocaleString('ru-RU')} золота
            </span>
          </ProfileCard>
        )}
        {law.encounter && !law.jail && (
          <p className="text-site-red text-xs">Стража остановила вас и ждёт ответа.</p>
        )}
        {law.wanted.length === 0 ? (
          <p className="text-white/50 text-xs flex items-center gap-1.5">
            <Shield size={14} className="text-white/30 shrink-0" />
            Вас нигде не разыскивают
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {law.wanted.map((w) => (
              <WantedRow key={w.region_id} wanted={w} />
            ))}
          </div>
        )}
      </>
    ) : null}
  </div>
);

/* ── Renown (FEAT-199) ── */

const RenownSection = ({
  renown,
  loading,
  error,
  onRetry,
}: {
  renown: RenownView | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) => {
  if (loading && !renown) {
    return (
      <div className="flex flex-col gap-2">
        <SectionHeader title="Слава" />
        <p className="text-white/40 text-xs">Загрузка...</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex flex-col gap-2">
        <SectionHeader title="Слава" />
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-site-red text-xs">{error}</span>
          <button type="button" className="btn-line !text-xs !py-1 !px-3" onClick={onRetry}>
            Повторить
          </button>
        </div>
      </div>
    );
  }
  if (!renown) return null;
  const { fame, rumors } = renown;
  const percent = fame.next_tier_name
    ? Math.round(Math.max(0, Math.min(1, fame.progress)) * 100)
    : 100;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
      <div className="flex flex-col gap-2 min-w-0">
        <SectionHeader title="Слава" />
        <ProfileCard className="p-3 flex flex-col gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Sparkles size={16} strokeWidth={1.8} className="text-gold shrink-0" />
            <span className="text-gold text-sm font-medium break-words min-w-0">{fame.tier_name}</span>
          </div>
          <div
            role="progressbar"
            aria-label={`Слава: ${fame.tier_name}`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
            className="stat-bar h-1.5 border-white/40"
          >
            <div
              className="stat-bar-fill bg-gradient-to-r from-gold-dark to-gold-light"
              style={{ width: `${percent}%` }}
            />
          </div>
          <p className="text-white/50 text-xs break-words">
            {fame.next_tier_name ? `Дальше: ${fame.next_tier_name}` : 'Выше славы не бывает'}
          </p>
          <p className="text-white/40 text-xs leading-snug">Чем громче имя, тем легче вас узнать.</p>
        </ProfileCard>
      </div>
      <div className="flex flex-col gap-2 min-w-0">
        <SectionHeader title="Слухи в подполье" />
        <ProfileCard className="p-3 flex flex-col gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <EyeOff size={16} strokeWidth={1.8} className="text-white/50 shrink-0" />
            <span className="text-white/80 text-sm font-medium break-words min-w-0">{rumors.tier_name}</span>
          </div>
          <p className="text-white/40 text-xs leading-snug">
            Что о вас шепчут в тёмных углах. Видно только вам.
          </p>
        </ProfileCard>
      </div>
    </div>
  );
};

/* ── Tier scale legend ── */

const TierScale = ({ tiers, current }: { tiers: ReputationTierBrief[]; current: Set<string> }) => (
  <div className="flex flex-wrap gap-1.5">
    {[...tiers]
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((tier) => {
        const tone = reputationTone(tier.code);
        const reached = current.has(tier.code);
        return (
          <span
            key={tier.code}
            className={`rounded-full border px-2.5 py-0.5 text-[11px] whitespace-nowrap ${REPUTATION_TONE_CHIP[tone]} ${
              reached ? 'bg-white/[0.07]' : 'opacity-60'
            }`}
          >
            {tier.name}
          </span>
        );
      })}
  </div>
);

/* ── Journal row ── */

const JournalRow = ({ item }: { item: ReputationHistoryItem }) => {
  const up = item.direction === 'up';
  return (
    <ProfileCard className="p-3 flex items-start gap-3">
      <div
        className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
          up ? 'bg-gold/15 text-gold' : 'bg-site-red/15 text-site-red'
        }`}
      >
        {up ? <ArrowUp size={16} /> : <ArrowDown size={16} />}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-white text-sm leading-relaxed break-words">{item.text}</p>
        <p className="text-white/50 text-xs mt-0.5 break-words">
          {item.action_name}
          {item.tier_changed && (
            <>
              {' · '}
              <span className={up ? 'text-gold' : 'text-site-red'}>теперь вы: {item.tier_after_name}</span>
            </>
          )}
        </p>
        <p className="text-white/30 text-xs mt-1">
          {formatRelativeTime(item.created_at, { style: 'long', yesterday: true })}
        </p>
      </div>
    </ProfileCard>
  );
};

/* ── Tab ── */

const ReputationTab = ({ characterId }: ReputationTabProps) => {
  const [regions, setRegions] = useState<ReputationRegion[]>([]);
  const [tiers, setTiers] = useState<ReputationTierBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [history, setHistory] = useState<ReputationHistoryItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const [law, setLaw] = useState<LawStateOut | null>(null);
  const [lawLoading, setLawLoading] = useState(true);
  const [lawError, setLawError] = useState<string | null>(null);

  const [renown, setRenown] = useState<RenownView | null>(null);
  const [renownLoading, setRenownLoading] = useState(true);
  const [renownError, setRenownError] = useState<string | null>(null);

  const loadRenown = useCallback(async () => {
    setRenownLoading(true);
    setRenownError(null);
    try {
      setRenown(await fetchRenown(characterId));
    } catch (err) {
      setRenownError(apiErrorMessage(err, 'Не удалось загрузить славу'));
    } finally {
      setRenownLoading(false);
    }
  }, [characterId]);

  const loadLaw = useCallback(async () => {
    setLawLoading(true);
    setLawError(null);
    try {
      setLaw(await fetchLawState(characterId));
    } catch (err) {
      setLawError(apiErrorMessage(err, 'Не удалось загрузить розыск'));
    } finally {
      setLawLoading(false);
    }
  }, [characterId]);

  const loadView = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchReputation(characterId);
      setRegions(data.regions);
      setTiers(data.tiers);
    } catch (err) {
      setError(apiErrorMessage(err, 'Не удалось загрузить репутацию'));
    } finally {
      setLoading(false);
    }
  }, [characterId]);

  const loadHistory = useCallback(
    async (page: number) => {
      setHistoryLoading(true);
      setHistoryError(null);
      try {
        const data = await fetchReputationHistory(characterId, page, HISTORY_PAGE_SIZE);
        setHistory((prev) => (page === 1 ? data.items : [...prev, ...data.items]));
        setHistoryTotal(data.total);
        setHistoryPage(page);
      } catch (err) {
        setHistoryError(apiErrorMessage(err, 'Не удалось загрузить журнал репутации'));
      } finally {
        setHistoryLoading(false);
      }
    },
    [characterId],
  );

  useEffect(() => {
    setHistory([]);
    loadView();
    loadHistory(1);
    loadLaw();
    loadRenown();
  }, [loadView, loadHistory, loadLaw, loadRenown]);

  const groups = useMemo(() => groupByCountry(regions), [regions]);
  const currentTiers = useMemo(() => new Set(regions.map((r) => r.tier_code)), [regions]);
  const hasMore = history.length < historyTotal;
  const startTierName = tiers.find((t) => t.code === START_TIER_CODE)?.name ?? 'Скиталец';

  const regionsIcon = <Scale size={18} strokeWidth={1.8} className="text-gold shrink-0" />;
  const journalIcon = <BookOpen size={18} strokeWidth={1.8} className="text-gold shrink-0" />;

  return (
    <motion.div {...TAB_MOTION} className="flex flex-col lg:flex-row gap-4 lg:gap-6">
      <PanelShell
        title="Репутация"
        icon={regionsIcon}
        className={`lg:flex-1 ${PANEL_DESKTOP_HEIGHT_CLASS}`}
      >
        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} onRetry={loadView} />
        ) : (
          <div className="flex flex-col gap-5">
            <RenownSection renown={renown} loading={renownLoading} error={renownError} onRetry={loadRenown} />
            <WantedSection law={law} loading={lawLoading} error={lawError} onRetry={loadLaw} />

            {tiers.length > 0 && (
              <div className="flex flex-col gap-2">
                <SectionHeader title="Ступени" />
                <TierScale tiers={tiers} current={currentTiers} />
                <p className="text-white/40 text-xs leading-snug">
                  Жители каждого края помнят ваши поступки. Полоска показывает, насколько вы близки к
                  следующей ступени.
                </p>
              </div>
            )}

            {groups.length === 0 ? (
              <EmptyState
                icon={<Scale size={32} strokeWidth={1.5} className="text-white/20" />}
                message="О вас пока нигде не слышали"
                hint={`Во всех краях вы — ${startTierName}. Выполняйте задания и помогайте жителям, чтобы заслужить их доверие.`}
              />
            ) : (
              groups.map((group) => (
                <div key={group.key} className="flex flex-col gap-2">
                  <SectionHeader title={group.name} />
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {group.regions.map((region) => (
                      <RegionRow key={region.region_id} region={region} />
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </PanelShell>

      <PanelShell
        title="Журнал"
        icon={journalIcon}
        headerExtra={!historyError && historyTotal > 0 ? <PanelCounter>{history.length}/{historyTotal}</PanelCounter> : undefined}
        className={`lg:w-[42%] lg:shrink-0 ${PANEL_DESKTOP_HEIGHT_CLASS}`}
      >
        {historyLoading && history.length === 0 ? (
          <LoadingState />
        ) : historyError && history.length === 0 ? (
          <ErrorState message={historyError} onRetry={() => loadHistory(1)} />
        ) : history.length === 0 ? (
          <EmptyState
            icon={<BookOpen size={32} strokeWidth={1.5} className="text-white/20" />}
            message="Записей пока нет"
            hint="Здесь появится, как к вам начинают относиться жители краёв"
          />
        ) : (
          <div className="flex flex-col gap-2">
            {history.map((item, idx) => (
              <JournalRow key={`${item.created_at}-${item.region_id}-${idx}`} item={item} />
            ))}
            {historyError && <p className="text-site-red text-xs text-center">{historyError}</p>}
            {hasMore && (
              <div className="flex justify-center pt-1">
                <button
                  type="button"
                  onClick={() => loadHistory(historyPage + 1)}
                  disabled={historyLoading}
                  className="btn-line w-full sm:w-auto px-6 py-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {historyLoading ? 'Загрузка...' : 'Загрузить ещё'}
                </button>
              </div>
            )}
          </div>
        )}
      </PanelShell>
    </motion.div>
  );
};

export default ReputationTab;
