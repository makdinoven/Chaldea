import { useMemo } from 'react';
import { AlertTriangle, Check, Coins, EyeOff, Flag, HandCoins, LogOut, X } from 'lucide-react';
import type { FactionMembership, FactionRankRequirement } from '../../../api/factions';
import { FACTION_MEMBER_STATUS_LABEL, FACTION_WEALTH_CLASS, secondsToDate, sumModifiers } from '../../../api/factions';
import { ModifierList, OutlawWarnings, PassiveRow } from './FactionPassives';
import RemainingText from '../../CommonComponents/RemainingText';
import { formatServerDate } from '../../../utils/serverDate';
import GoldIconFrame from '../shared/GoldIconFrame';
import ProfileCard from '../shared/ProfileCard';

/* ── Emblem ── */

export const FactionEmblem = ({ src, size = 48 }: { src: string | null; size?: number }) => (
  <GoldIconFrame
    size={size}
    src={src ?? undefined}
    alt=""
    fallback={<Flag size={Math.round(size * 0.42)} strokeWidth={1.6} className="text-gold/70" />}
  />
);

/* ── One requirement row (✓ / ✗) ── */

export const RequirementRow = ({ met, text }: { met: boolean | null; text: string }) => (
  <li className="flex items-start gap-2 text-xs leading-snug min-w-0">
    {met === null ? (
      <span className="mt-[3px] w-3.5 h-3.5 shrink-0 rounded-full border border-white/25" aria-hidden />
    ) : met ? (
      <Check size={14} strokeWidth={2.2} className="mt-px shrink-0 text-stat-energy" aria-label="выполнено" />
    ) : (
      <X size={14} strokeWidth={2.2} className="mt-px shrink-0 text-site-red" aria-label="не выполнено" />
    )}
    <span className={`break-words min-w-0 ${met === false ? 'text-white/60' : 'text-white/85'}`}>{text}</span>
  </li>
);

/* ── Next rank ── */

const NextRankProgress = ({ name, conditions }: { name: string; conditions: FactionRankRequirement[] }) => {
  const done = conditions.filter((c) => c.met).length;
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-white/50 text-xs">
        Следующее звание: <span className="text-gold-light">{name}</span>
        {conditions.length > 0 && (
          <span className="text-white/40 font-mono tabular-nums">
            {' '}
            · {done}/{conditions.length}
          </span>
        )}
      </p>
      {conditions.length > 0 ? (
        <ul className="flex flex-col gap-1">
          {conditions.map((c) => (
            <RequirementRow key={`${c.type}-${c.text}`} met={c.met} text={c.text} />
          ))}
        </ul>
      ) : (
        <p className="text-white/40 text-xs">Условий нет — звание придёт само.</p>
      )}
    </div>
  );
};

/* ── Warning (conditions no longer met) ── */

const FactionWarningBanner = ({ reasons, until }: { reasons: string[]; until: Date | null }) => (
  <div className="rounded-card border border-site-red/30 bg-site-red/[0.06] p-3 flex flex-col gap-1.5">
    <p className="text-site-red text-xs font-medium flex items-center gap-1.5">
      <AlertTriangle size={14} className="shrink-0" />
      Вы перестали соответствовать условиям фракции
    </p>
    {reasons.length > 0 && (
      <ul className="flex flex-col gap-1">
        {reasons.map((r) => (
          <RequirementRow key={r} met={false} text={r} />
        ))}
      </ul>
    )}
    <p className="text-white/70 text-xs">
      Исправьте, иначе вас исключат:{' '}
      <RemainingText until={until} prefix="осталось" doneText="срок вышел — исключение при ближайшей проверке" className="text-gold-light" />
    </p>
  </div>
);

/* ── FEAT-206: the faction's debt to the character (a number — it is the player's money) ── */

export const FactionDebtNote = ({ debt }: { debt: number | undefined }) =>
  debt && debt > 0 ? (
    <p className="rounded-card border border-gold/25 bg-gold/[0.05] px-3 py-2 text-xs text-white/80 flex items-start gap-1.5">
      <Coins size={14} className="text-gold shrink-0 mt-px" />
      <span>
        Фракция должна вам: <span className="gold-text font-medium font-mono tabular-nums">{debt.toLocaleString('ru-RU')}</span>{' '}
        марок. Выплатят, когда казна пополнится.
      </span>
    </p>
  ) : null;

/* ── Active membership ── */

interface FactionMembershipCardProps {
  membership: FactionMembership;
  onLeave: (membership: FactionMembership) => void;
  /** FEAT-206: opens the donation dialog. */
  onDonate?: (membership: FactionMembership) => void;
}

const FactionMembershipCard = ({ membership, onLeave, onDonate }: FactionMembershipCardProps) => {
  const m = membership;
  // The countdown target is fixed when the data arrives, not on every render.
  const warningUntil = useMemo(() => secondsToDate(m.warning?.remaining_seconds), [m.warning?.remaining_seconds]);
  // FEAT-207: passives of all ranks up to the held one (cumulative).
  const passives = m.passives ?? [];
  const passiveSum = useMemo(() => sumModifiers((m.passives ?? []).map((p) => p.modifiers)), [m.passives]);
  const canDonate = !!m.donation && (m.donation.enabled || !!m.donation.items_enabled);

  return (
    <ProfileCard className="p-3.5 flex flex-col gap-3" variant={m.warning ? 'danger' : 'default'}>
      <div className="flex items-start gap-3 min-w-0">
        <FactionEmblem src={m.faction.emblem_url} />
        <div className="flex-1 min-w-0 flex flex-col gap-0.5">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 min-w-0">
            <span className="text-white text-sm sm:text-base font-medium break-words min-w-0">{m.faction.name}</span>
            {m.faction.is_secret && (
              <span
                className="inline-flex items-center gap-1 rounded-full border border-white/15 px-2 py-px text-[10px] text-white/60"
                title="Членство видно только вам"
              >
                <EyeOff size={11} />
                тайная
              </span>
            )}
          </div>
          <p className="text-gold text-sm break-words">{m.rank?.name ?? 'Без звания'}</p>
          {m.rank_title?.name && (
            <p className="text-white/50 text-xs break-words">
              Титул за звание: <span className="text-white/80">{m.rank_title.name}</span>
            </p>
          )}
          {m.wealth && (
            <p className="text-white/50 text-xs break-words">
              Казна: <span className={FACTION_WEALTH_CLASS[m.wealth.state] ?? 'text-white/80'}>{m.wealth.label}</span>
            </p>
          )}
        </div>
        <div className="shrink-0 text-right">
          <p className="gold-text text-xl font-medium font-mono tabular-nums leading-none">{m.points}</p>
          <p className="text-white/40 text-[11px] mt-1">очков</p>
        </div>
      </div>

      {m.warning && <FactionWarningBanner reasons={m.warning.reasons} until={warningUntil} />}

      <FactionDebtNote debt={m.debt} />

      <OutlawWarnings regions={m.outlaw_regions} />

      {passives.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Пассивки (в бою)</p>
          {passives.map((p) => (
            <PassiveRow key={p.rank_id} name={p.name} description={p.description} modifiers={p.modifiers} rankName={p.rank_name} />
          ))}
          {passives.length > 1 && Object.keys(passiveSum).length > 0 && (
            <div className="flex flex-col gap-1 pt-1 border-t border-white/[0.06]">
              <p className="text-white/45 text-[11px]">Итого от фракции:</p>
              <ModifierList modifiers={passiveSum} />
            </div>
          )}
        </div>
      )}

      {m.next_rank ? (
        <NextRankProgress name={m.next_rank.name} conditions={m.next_rank.conditions} />
      ) : (
        m.rank && <p className="text-white/40 text-xs">Высшее звание фракции.</p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-white/[0.06]">
        <span className="text-white/35 text-[11px]">
          {m.joined_at ? `В составе с ${formatServerDate(m.joined_at)}` : ''}
        </span>
        <span className="flex items-center gap-3 ml-auto">
          {onDonate && canDonate && (
            <button
              type="button"
              onClick={() => onDonate(m)}
              className="text-xs text-white/60 hover:text-gold transition-colors duration-200 ease-site inline-flex items-center gap-1 min-h-[32px]"
            >
              <HandCoins size={13} />
              Пожертвовать
            </button>
          )}
          <button
            type="button"
            onClick={() => onLeave(m)}
            className="text-xs text-white/50 hover:text-site-red transition-colors duration-200 ease-site inline-flex items-center gap-1 min-h-[32px]"
          >
            <LogOut size={13} />
            Покинуть
          </button>
        </span>
      </div>
    </ProfileCard>
  );
};

/* ── Former membership (left / expelled) ── */

export const FormerMembershipRow = ({ membership }: { membership: FactionMembership }) => {
  const m = membership;
  const rejoinAt = useMemo(() => secondsToDate(m.rejoin_in_seconds), [m.rejoin_in_seconds]);
  const status = m.status === 'active' ? null : FACTION_MEMBER_STATUS_LABEL[m.status];
  return (
    <ProfileCard className="p-3 flex items-center gap-3" locked>
      <FactionEmblem src={m.faction.emblem_url} size={36} />
      <div className="flex-1 min-w-0 flex flex-col gap-1">
        <p className="text-white text-sm break-words">{m.faction.name}</p>
        <p className="text-white/50 text-xs break-words">
          {status}
          {m.rank?.name ? ` · бывш. звание «${m.rank.name}»` : ''} · очков: {m.points}
        </p>
        <p className="text-white/45 text-xs">
          {rejoinAt ? (
            <RemainingText until={rejoinAt} prefix="вступить снова можно — осталось" doneText="можно вступить снова" />
          ) : (
            'можно вступить снова'
          )}
        </p>
        <FactionDebtNote debt={m.debt} />
      </div>
    </ProfileCard>
  );
};

export default FactionMembershipCard;
