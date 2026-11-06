import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';
import {
  FACTION_MEMBER_STATUS_LABEL,
  adminListMembers,
  secondsToDate,
  type FactionMemberAdmin,
  type FactionMemberStatus,
  type FactionPage,
} from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import useDebounce from '../../../hooks/useDebounce';
import { formatServerDate } from '../../../utils/serverDate';
import RemainingText from '../../CommonComponents/RemainingText';
import { FIELD, LABEL, OPTION, useFactionOptions } from './adminShared';
import { Pager } from './ApplicationsTab';
import MemberActionModal, { type MemberActionTarget } from './MemberActionModal';

const PAGE_SIZE = 20;
const STATUSES: (FactionMemberStatus | 'all')[] = ['active', 'left', 'expelled', 'all'];

const WarningLine = ({ m }: { m: FactionMemberAdmin }) => {
  const until = useMemo(() => secondsToDate(m.warning?.remaining_seconds), [m.warning?.remaining_seconds]);
  if (!m.warning) return null;
  return (
    <p className="text-site-red text-xs flex items-start gap-1.5 break-words">
      <AlertTriangle size={13} className="shrink-0 mt-px" />
      <span>
        Предупреждение: {m.warning.reasons.join('; ') || 'условия не выполнены'} ·{' '}
        <RemainingText until={until} prefix="до исключения осталось" doneText="срок вышел" />
      </span>
    </p>
  );
};

/** Members of one faction: search, status filter, points ± and expel (factions:manage). */
const MembersTab = ({ canManage }: { canManage: boolean }) => {
  const { factions, error: factionsError } = useFactionOptions();
  const [factionId, setFactionId] = useState<number | ''>('');
  const [status, setStatus] = useState<FactionMemberStatus | 'all'>('active');
  const [query, setQuery] = useState('');
  const debounced = useDebounce(query, 300) as string;
  const [page, setPage] = useState(1);
  const [data, setData] = useState<FactionPage<FactionMemberAdmin> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [action, setAction] = useState<MemberActionTarget | null>(null);

  useEffect(() => {
    if (factionId === '' && factions.length > 0) setFactionId(factions[0].id);
  }, [factions, factionId]);

  const factionName = factions.find((f) => f.id === factionId)?.name ?? '';

  const load = useCallback(async () => {
    if (factionId === '') return;
    setLoading(true);
    setError(null);
    try {
      setData(await adminListMembers(factionId, { status, q: debounced, page, page_size: PAGE_SIZE }));
    } catch (e) {
      setError(apiErrorMessage(e, 'Не удалось загрузить участников'));
    } finally {
      setLoading(false);
    }
  }, [factionId, status, debounced, page]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row gap-3">
        <label className="flex flex-col gap-1 sm:w-72">
          <span className={LABEL}>Фракция</span>
          <select
            value={factionId}
            onChange={(e) => {
              setFactionId(e.target.value ? Number(e.target.value) : '');
              setPage(1);
            }}
            className={FIELD}
          >
            {factions.length === 0 && <option value="" className={OPTION}>— нет фракций —</option>}
            {factions.map((f) => (
              <option key={f.id} value={f.id} className={OPTION}>
                {f.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 sm:w-48">
          <span className={LABEL}>Статус</span>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as FactionMemberStatus | 'all');
              setPage(1);
            }}
            className={FIELD}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s} className={OPTION}>
                {s === 'all' ? 'Все' : FACTION_MEMBER_STATUS_LABEL[s]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 sm:flex-1">
          <span className={LABEL}>Поиск по имени</span>
          <input
            value={query}
            maxLength={100}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            className={FIELD}
            placeholder="Имя персонажа..."
          />
        </label>
      </div>

      {factionsError && <p className="text-site-red text-sm">{factionsError}</p>}
      {error && <p className="text-site-red text-sm">{error}</p>}
      {loading && !data && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
      {data?.items.length === 0 && <p className="text-white/50 text-sm">Участников не найдено.</p>}

      <div className="flex flex-col gap-2">
        {data?.items.map((m) => (
          <div key={m.membership_id} className="flex flex-col gap-2 bg-white/[0.03] border border-white/[0.06] rounded-card p-3">
            <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
              <div className="flex items-center gap-3 min-w-0 flex-1">
                <span className="w-9 h-9 rounded-full overflow-hidden bg-black/40 shrink-0">
                  {m.character.avatar && <img src={m.character.avatar} alt="" className="w-full h-full object-cover" />}
                </span>
                <div className="min-w-0">
                  <Link to={`/admin/characters/${m.character.id}`} className="site-link text-sm break-words">
                    {m.character.name ?? `#${m.character.id}`}
                  </Link>
                  <p className="text-white/50 text-xs break-words">
                    ур. {m.character.level ?? '—'} · {FACTION_MEMBER_STATUS_LABEL[m.status]} · {m.rank?.name ?? 'без звания'} ·{' '}
                    <span className="text-gold">{m.points} очк.</span>
                    {m.joined_at ? ` · с ${formatServerDate(m.joined_at)}` : ''}
                  </p>
                </div>
              </div>
              {canManage && m.status === 'active' && (
                <div className="flex gap-4 shrink-0">
                  <button
                    type="button"
                    onClick={() =>
                      setAction({ mode: 'points', membershipId: m.membership_id, characterName: m.character.name ?? `#${m.character.id}`, factionName, points: m.points })
                    }
                    className="text-sm text-white hover:text-site-blue transition-colors"
                  >
                    Очки ±
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setAction({ mode: 'expel', membershipId: m.membership_id, characterName: m.character.name ?? `#${m.character.id}`, factionName, points: m.points })
                    }
                    className="text-sm text-site-red hover:text-white transition-colors"
                  >
                    Исключить
                  </button>
                </div>
              )}
            </div>
            <WarningLine m={m} />
          </div>
        ))}
      </div>
      {data && <Pager page={page} total={data.total} pageSize={PAGE_SIZE} onPage={setPage} />}

      <MemberActionModal
        target={action}
        onClose={() => setAction(null)}
        onDone={() => {
          setAction(null);
          void load();
        }}
      />
    </div>
  );
};

export default MembersTab;
