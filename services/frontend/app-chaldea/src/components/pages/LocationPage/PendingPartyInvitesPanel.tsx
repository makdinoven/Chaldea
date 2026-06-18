import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  fetchIncomingPartyInvites,
  respondToParty,
  type IncomingPartyInvite,
} from '../../../api/party';
import PartyLobbyModal from './PartyLobbyModal';

interface PendingPartyInvitesPanelProps {
  characterId: number;
  locationId: number;
}

const POLL_MS = 8000;
const BTYPE_LABEL: Record<string, string> = {
  pvp_training: 'Тренировка',
  pvp_death: 'Смертельный',
};

const PendingPartyInvitesPanel = ({
  characterId,
  locationId,
}: PendingPartyInvitesPanelProps) => {
  const [invites, setInvites] = useState<IncomingPartyInvite[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [openPartyId, setOpenPartyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setInvites(await fetchIncomingPartyInvites());
    } catch {
      /* ignore — transient */
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const respond = async (partyId: number, action: 'accept' | 'decline') => {
    setBusyId(partyId);
    try {
      await respondToParty(partyId, characterId, action);
      await load();
      if (action === 'accept') setOpenPartyId(partyId);
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast.error(err?.response?.data?.detail || 'Не удалось ответить на приглашение');
    } finally {
      setBusyId(null);
    }
  };

  if (invites.length === 0 && openPartyId === null) return null;

  return (
    <>
      {invites.length > 0 && (
        <section className="bg-black/60 rounded-card p-4 flex flex-col gap-2">
          <h3 className="gold-text text-sm uppercase font-medium">
            Приглашения в группу
          </h3>
          {invites.map((inv) => (
            <div
              key={inv.party_id}
              className="flex items-center gap-2 bg-white/5 rounded-card p-2"
            >
              <div className="flex-1 min-w-0">
                <p className="text-white text-sm truncate">{inv.leader_name}</p>
                <p className="text-white/40 text-xs">
                  {BTYPE_LABEL[inv.battle_type] ?? inv.battle_type} · команда{' '}
                  {inv.team + 1} · {inv.member_count} в группе
                </p>
              </div>
              <button
                onClick={() => respond(inv.party_id, 'accept')}
                disabled={busyId === inv.party_id}
                className="btn-blue text-xs px-3 py-1.5 disabled:opacity-40"
              >
                Принять
              </button>
              <button
                onClick={() => respond(inv.party_id, 'decline')}
                disabled={busyId === inv.party_id}
                className="btn-line text-xs px-3 py-1.5 disabled:opacity-40"
              >
                Отклонить
              </button>
            </div>
          ))}
        </section>
      )}

      {openPartyId !== null && (
        <PartyLobbyModal
          characterId={characterId}
          locationId={locationId}
          players={[]}
          initialPartyId={openPartyId}
          onClose={() => setOpenPartyId(null)}
        />
      )}
    </>
  );
};

export default PendingPartyInvitesPanel;
