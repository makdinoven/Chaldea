import { LogOut } from 'lucide-react';
import type { FactionMembership, FactionPlayerSettings } from '../../../api/factions';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import LoadingState from '../shared/LoadingState';

interface LeaveFactionDialogProps {
  membership: FactionMembership | null;
  settings: FactionPlayerSettings | null;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

const daysText = (n: number): string => {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n} день`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} дня`;
  return `${n} дней`;
};

/** «Покинуть фракцию» — states the cooldown and the burned share before the player agrees. */
const LeaveFactionDialog = ({ membership, settings, busy, onCancel, onConfirm }: LeaveFactionDialogProps) => {
  const burnPct = settings?.leave_burn_pct ?? 0;
  const cooldown = settings?.rejoin_cooldown_days ?? 0;
  const points = membership?.points ?? 0;
  const kept = Math.floor((points * (100 - burnPct)) / 100);

  return (
    <ModalShell
      open={membership !== null}
      onClose={onCancel}
      title="Покинуть фракцию"
      icon={<LogOut size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
      size="sm"
      dismissible={!busy}
      footer={
        <>
          <button type="button" className="btn-line w-full sm:w-auto" onClick={onCancel} disabled={busy}>
            Остаться
          </button>
          <button
            type="button"
            className="btn-blue w-full sm:w-auto disabled:opacity-50"
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? <LoadingState size="xs" /> : 'Покинуть'}
          </button>
        </>
      }
    >
      {membership && (
        <div className="flex flex-col gap-3 text-sm text-white/85">
          <p>
            Вы покидаете фракцию <span className="text-gold">«{membership.faction.name}»</span>.
          </p>
          <ul className="flex flex-col gap-1.5 list-disc pl-5 text-white/75">
            <li>
              {cooldown > 0
                ? `Вступить снова можно будет не раньше чем через ${daysText(cooldown)}.`
                : 'Вступить снова можно будет сразу.'}
            </li>
            <li>
              {burnPct > 0
                ? `Сгорит ${burnPct}% очков: из ${points} останется ${kept}.`
                : `Очки сохранятся (${points}).`}
            </li>
            <li>Звание при возвращении пересчитают по оставшимся очкам; награды за уже полученные звания второй раз не выдаются.</li>
          </ul>
        </div>
      )}
    </ModalShell>
  );
};

export default LeaveFactionDialog;
