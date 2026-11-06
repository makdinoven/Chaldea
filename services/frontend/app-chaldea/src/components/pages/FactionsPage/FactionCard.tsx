import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { ChevronDown, Coins, Crown, EyeOff, Flag, MapPin, Users } from 'lucide-react';
import type { FactionCatalogItem } from '../../../api/factions';
import { FACTION_WEALTH_CLASS, secondsToDate } from '../../../api/factions';
import RemainingText from '../../CommonComponents/RemainingText';
import { factionConditionText, replaceSubclassKeys } from '../../../utils/factionText';
import { RequirementRow } from '../../ProfilePage/FactionsTab/FactionMembershipCard';
import { OutlawWarnings, PassiveRow } from '../../ProfilePage/FactionsTab/FactionPassives';

interface FactionCardProps {
  faction: FactionCatalogItem;
  /** No active character: conditions without ✓/✗, no action. */
  hasCharacter: boolean;
  busy: boolean;
  subclassNames: Record<string, string>;
  onJoin: (faction: FactionCatalogItem) => void;
  onApply: (faction: FactionCatalogItem) => void;
  onCancelApplication: (faction: FactionCatalogItem) => void;
}

const Badge = ({ children, title }: { children: ReactNode; title?: string }) => (
  <span
    title={title}
    className="inline-flex items-center gap-1 rounded-full border border-white/15 px-2 py-0.5 text-[11px] text-white/70 whitespace-nowrap"
  >
    {children}
  </span>
);

const membersText = (f: FactionCatalogItem): string | null => {
  if (f.member_count == null) return null;
  return f.member_limit != null ? `${f.member_count} / ${f.member_limit}` : String(f.member_count);
};

/** The action area: join / apply / pending / cooldown / blocked / member. */
const FactionAction = ({
  faction,
  hasCharacter,
  busy,
  onJoin,
  onApply,
  onCancelApplication,
  subclassNames,
}: FactionCardProps) => {
  const my = faction.my;
  const rejoinAt = useMemo(() => secondsToDate(my?.rejoin_in_seconds), [my?.rejoin_in_seconds]);
  const reapplyAt = useMemo(() => secondsToDate(my?.reapply_in_seconds), [my?.reapply_in_seconds]);

  if (!hasCharacter) {
    return <p className="text-white/50 text-xs">Выберите персонажа, чтобы вступить во фракцию.</p>;
  }
  if (my?.status === 'active') {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-stat-energy text-sm">Вы состоите</span>
        {my.rank_name && <span className="text-gold text-sm">· {my.rank_name}</span>}
        <Link to="/profile" className="site-link text-xs ml-auto">
          Вкладка «Фракции» в профиле
        </Link>
      </div>
    );
  }
  if (my?.status === 'pending') {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-gold-light text-sm">Заявка на рассмотрении</span>
        {my.application_id && (
          <button
            type="button"
            disabled={busy}
            onClick={() => onCancelApplication(faction)}
            className="btn-line !w-full sm:!w-auto !text-xs !py-1.5 !px-4 sm:ml-auto disabled:opacity-50"
          >
            Отозвать заявку
          </button>
        )}
      </div>
    );
  }
  if (rejoinAt) {
    return (
      <p className="text-white/60 text-xs">
        Повторное вступление:{' '}
        <RemainingText until={rejoinAt} doneText="уже можно — обновите страницу" className="text-gold-light" />
      </p>
    );
  }
  if (faction.is_invite_only && reapplyAt) {
    return (
      <p className="text-white/60 text-xs">
        Повторная заявка:{' '}
        <RemainingText until={reapplyAt} doneText="уже можно — обновите страницу" className="text-gold-light" />
      </p>
    );
  }
  const label = faction.is_invite_only ? 'Подать заявку' : 'Вступить';
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-2">
      <button
        type="button"
        disabled={!faction.can_join || busy}
        onClick={() => (faction.is_invite_only ? onApply(faction) : onJoin(faction))}
        className="btn-blue !w-full sm:!w-auto !text-sm !py-2 !px-6 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {label}
      </button>
      {!faction.can_join && faction.join_block_reason && (
        <span className="text-white/55 text-xs">{replaceSubclassKeys(faction.join_block_reason, subclassNames)}</span>
      )}
    </div>
  );
};

/** One faction in the catalog: summary always, the rest (description, leaders, ranks, conditions) on demand. */
const FactionCard = (props: FactionCardProps) => {
  const { faction, hasCharacter, subclassNames } = props;
  const [open, setOpen] = useState(false);
  const members = membersText(faction);
  const conditionsMet = faction.conditions.filter((c) => c.met === true).length;
  const ranks = [...faction.ranks].sort((a, b) => a.sort_order - b.sort_order);
  const rankPassives = ranks.flatMap((rank) =>
    rank.passive && Object.keys(rank.passive.modifiers ?? {}).length > 0 ? [{ rank, passive: rank.passive }] : [],
  );
  const outlaw = faction.outlaw_regions ?? [];

  return (
    <motion.article
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className="gold-outline relative rounded-card bg-site-bg backdrop-blur-[10px] shadow-card p-4 sm:p-5 flex flex-col gap-4 min-w-0"
    >
      <div className="flex items-start gap-3 sm:gap-4 min-w-0">
        <div className="w-14 h-14 sm:w-16 sm:h-16 shrink-0 rounded-[10px] p-[2px] bg-gradient-to-b from-gold-light to-gold-dark">
          <div className="w-full h-full rounded-[8px] bg-site-dark flex items-center justify-center overflow-hidden">
            {faction.emblem_url ? (
              <img src={faction.emblem_url} alt="" className="w-full h-full object-cover" />
            ) : (
              <Flag size={26} strokeWidth={1.6} className="text-gold/70" />
            )}
          </div>
        </div>
        <div className="flex-1 min-w-0 flex flex-col gap-1.5">
          <h2 className="gold-text text-lg sm:text-xl font-medium uppercase tracking-[0.04em] break-words">{faction.name}</h2>
          <div className="flex flex-wrap gap-1.5">
            {faction.is_invite_only && <Badge title="Вступление через заявку, её рассматривает администрация">по заявке</Badge>}
            {faction.is_secret && (
              <Badge title="Членство видно только самому участнику">
                <EyeOff size={11} />
                тайная
              </Badge>
            )}
            {members && (
              <Badge title="Участников">
                <Users size={11} />
                {members}
              </Badge>
            )}
            {faction.wealth && (
              <Badge title="Состояние казны фракции">
                <Coins size={11} />
                <span className={FACTION_WEALTH_CLASS[faction.wealth.state] ?? ''}>{faction.wealth.label}</span>
              </Badge>
            )}
            {hasCharacter && faction.conditions.length > 0 && (
              <Badge title="Выполнено условий вступления">
                условия {conditionsMet}/{faction.conditions.length}
              </Badge>
            )}
          </div>
        </div>
      </div>

      {outlaw.length > 0 && <OutlawWarnings regions={outlaw} compact={!open} />}

      {faction.description && (
        <p className={`text-white/75 text-sm whitespace-pre-wrap break-words ${open ? '' : 'line-clamp-3'}`}>
          {faction.description}
        </p>
      )}

      {open && (
        <div className="flex flex-col gap-4">
          {(faction.hq_location || faction.leaders.length > 0) && (
            <div className="flex flex-col gap-1.5 text-sm">
              {faction.hq_location && (
                <p className="text-white/70 flex items-center gap-1.5 min-w-0">
                  <MapPin size={14} className="text-gold shrink-0" />
                  Штаб:{' '}
                  <Link to={`/location/${faction.hq_location.id}`} className="site-link truncate">
                    {faction.hq_location.name ?? `Локация #${faction.hq_location.id}`}
                  </Link>
                </p>
              )}
              {faction.leaders.length > 0 && (
                <p className="text-white/70 flex items-start gap-1.5 min-w-0">
                  <Crown size={14} className="text-gold shrink-0 mt-0.5" />
                  <span className="break-words">
                    Руководство: {faction.leaders.map((l) => l.name ?? `#${l.id}`).join(', ')}
                  </span>
                </p>
              )}
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <p className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Условия вступления</p>
            {faction.conditions.length === 0 ? (
              <p className="text-white/50 text-xs">Особых условий нет.</p>
            ) : (
              <ul className="flex flex-col gap-1">
                {faction.conditions.map((c, i) => (
                  <RequirementRow key={`${c.type}-${i}`} met={c.met} text={factionConditionText(c, subclassNames)} />
                ))}
              </ul>
            )}
          </div>

          {ranks.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <p className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Звания</p>
              <ol className="flex flex-wrap gap-1.5">
                {ranks.map((r, i) => (
                  <li key={r.id} className="rounded-full border border-gold/25 px-2.5 py-0.5 text-[11px] text-gold-light">
                    {i + 1}. {r.name}
                  </li>
                ))}
              </ol>
              {/* FEAT-207: what each rank's passive gives (cumulative while the rank is held) */}
              {rankPassives.length > 0 && (
                <div className="flex flex-col gap-2 pt-1">
                  <p className="text-white/40 text-[11px]">Пассивки званий действуют в бою и складываются с пассивками младших званий:</p>
                  {rankPassives.map(({ rank, passive }) => (
                    <PassiveRow
                      key={rank.id}
                      name={passive.name}
                      description={passive.description}
                      modifiers={passive.modifiers}
                      rankName={rank.name}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="self-start text-xs text-white/55 hover:text-site-blue transition-colors duration-200 ease-site inline-flex items-center gap-1"
      >
        {open ? 'Свернуть' : 'Подробнее: условия, звания, руководство'}
        <ChevronDown size={14} className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>

      <div className="pt-3 border-t border-white/[0.07]">
        <FactionAction {...props} />
      </div>
    </motion.article>
  );
};

export default FactionCard;
