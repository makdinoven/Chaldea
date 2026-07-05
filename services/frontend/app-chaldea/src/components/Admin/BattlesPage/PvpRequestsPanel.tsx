import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  listPvpRequests,
  approvePvpRequest,
  rejectPvpRequest,
  type PvpRequest,
} from '../../../api/battles';

// Forced-PvP approval queue (FEAT-145 §7): a no-consent attack waits here until
// an admin approves it into a battle.
const PvpRequestsPanel = () => {
  const [requests, setRequests] = useState<PvpRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setRequests(await listPvpRequests());
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Не удалось загрузить заявки');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const act = async (id: number, approve: boolean) => {
    if (busyId) return;
    setBusyId(id);
    try {
      if (approve) {
        await approvePvpRequest(id);
        toast.success('Бой создан');
      } else {
        await rejectPvpRequest(id);
        toast.success('Заявка отклонена');
      }
      await reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setBusyId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="w-7 h-7 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (requests.length === 0) {
    return <p className="text-white/50 text-sm py-8">Нет заявок на принудительное PvP.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      {requests.map((r) => (
        <div
          key={r.id}
          className="flex items-center justify-between gap-3 bg-white/[0.04] rounded-card p-4"
        >
          <div className="min-w-0">
            <p className="text-white">
              <span className="text-site-red">{r.attacker_name ?? `#${r.attacker_character_id}`}</span>
              {' → '}
              <span className="gold-text">{r.victim_name ?? `#${r.victim_character_id}`}</span>
            </p>
            <p className="text-white/40 text-xs">
              Локация #{r.location_id} · {r.battle_type ?? 'pvp_death'}
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              type="button"
              disabled={busyId === r.id}
              onClick={() => act(r.id, true)}
              className="px-3 py-1.5 rounded-lg border border-emerald-400/40 text-emerald-300 text-sm hover:bg-emerald-400/10 transition disabled:opacity-50"
            >
              Одобрить
            </button>
            <button
              type="button"
              disabled={busyId === r.id}
              onClick={() => act(r.id, false)}
              className="px-3 py-1.5 rounded-lg border border-white/15 text-white/60 text-sm hover:bg-white/5 transition disabled:opacity-50"
            >
              Отклонить
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};

export default PvpRequestsPanel;
