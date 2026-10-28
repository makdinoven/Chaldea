import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Home, MapPin, Orbit } from 'lucide-react';
import { getHomeTeleportTargets, homeTeleport, percentText, type HomeTeleportTarget } from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import { useAppDispatch } from '../../../redux/store';
import { getMe, setCharacterLocation } from '../../../redux/slices/userSlice';
import { fetchInventory } from '../../../redux/slices/profileSlice';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';

/*
  FEAT-180 stage 6b — reading a home teleport scroll: pick one of the houses
  whose return circle the character may use, confirm, and the character moves
  to that house's location, standing in its return circle (stage 7). The
  circle may keep the scroll.
*/

interface HomeTeleportModalProps {
  characterId: number;
  inventoryItemId: number;
  scrollName: string;
  onClose: () => void;
}

const HomeTeleportModal = ({ characterId, inventoryItemId, scrollName, onClose }: HomeTeleportModalProps) => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const [targets, setTargets] = useState<HomeTeleportTarget[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    getHomeTeleportTargets(characterId)
      .then((list) => {
        if (!alive) return;
        setTargets(list);
        if (list.length === 1) setPicked(list[0].house_id);
      })
      .catch((e) => {
        if (!alive) return;
        const msg = apiErrorMessage(e, 'Не удалось загрузить дома');
        setError(msg);
        toast.error(msg);
      });
    return () => {
      alive = false;
    };
  }, [characterId]);

  const target = targets?.find((t) => t.house_id === picked) ?? null;

  const go = async () => {
    if (!target) return;
    setBusy(true);
    try {
      const r = await homeTeleport(characterId, inventoryItemId, target.house_id);
      const where = r.location_name ?? target.location_name ?? target.name;
      toast.success(`Вы перенеслись в «${where}». ${r.scroll_kept ? 'Свиток сохранился' : 'Свиток израсходован'}`);
      dispatch(setCharacterLocation({ id: r.location_id, name: where }));
      void dispatch(getMe());
      void dispatch(fetchInventory(characterId));
      onClose();
      // Stage 7: the character lands in the house's return circle — open the house from inside.
      const houseId = r.house_id ?? target.house_id;
      navigate(r.house_room_id != null ? `/houses/${houseId}/room/${r.house_room_id}` : `/houses/${houseId}`);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось прочесть свиток'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalShell open onClose={onClose} title="Вернуться домой" icon={<Orbit size={18} className="text-gold" />}
      size="md" dismissible={!busy}
      footer={targets != null && targets.length > 0 ? (
        <>
          <button type="button" onClick={onClose} disabled={busy} className="btn-line !w-full sm:!w-auto !px-6 disabled:opacity-50">
            Отмена
          </button>
          <button type="button" onClick={() => void go()} disabled={busy || !target}
            className="btn-blue !w-full sm:!w-auto !px-6 disabled:opacity-50">
            {busy ? 'Перенос...' : 'Прочесть свиток'}
          </button>
        </>
      ) : undefined}>
      <div className="flex flex-col gap-3">
        <p className="text-white/60 text-sm">
          «{scrollName}» перенесёт персонажа в локацию дома с построенным кругом возвращения.
        </p>
        {error && <p className="text-site-red text-sm">{error}</p>}
        {!error && targets == null && (
          <div className="w-7 h-7 border-4 border-white/30 border-t-gold rounded-full animate-spin mx-auto" />
        )}
        {targets != null && targets.length === 0 && (
          <p className="text-white/70 text-sm bg-white/[0.03] border border-white/[0.08] rounded-card p-3 leading-relaxed">
            Свитку некуда вас перенести. Нужен построенный круг возвращения в вашем доме — или в доме, где вы живёте
            и куда хозяин пустил вас в круг.
          </p>
        )}
        {targets != null && targets.length > 0 && (
          <div className="flex flex-col gap-2">
            {targets.map((t) => {
              const active = t.house_id === picked;
              return (
                <button key={t.house_id} type="button" disabled={busy} onClick={() => setPicked(t.house_id)}
                  className={`flex items-center gap-3 p-3 rounded-card border text-left transition-colors duration-200 ease-site min-w-0 disabled:opacity-50 ${
                    active ? 'border-gold/70 bg-gold/[0.08]' : 'border-white/[0.08] bg-white/[0.03] hover:border-gold/40'
                  }`}>
                  <Home size={18} className={`shrink-0 ${active ? 'text-gold' : 'text-white/50'}`} />
                  <span className="flex flex-col gap-0.5 min-w-0 flex-1">
                    <span className="text-white text-sm leading-tight break-words">{t.name}</span>
                    <span className="flex items-center gap-1 text-white/50 text-[11px] min-w-0">
                      <MapPin size={11} className="shrink-0" />
                      <span className="truncate">{t.location_name ?? `Локация #${t.location_id}`}</span>
                    </span>
                    <span className="text-gold-light/80 text-[11px]">
                      Круг ур. {t.circle_level} · {t.keep_chance > 0
                        ? `свиток сохранится с шансом ${percentText(t.keep_chance)} %`
                        : 'свиток будет израсходован'}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </ModalShell>
  );
};

export default HomeTeleportModal;
