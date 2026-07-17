// ProfilePage PartyTab — redesigned per Claude Design mock (FEAT-151),
// party system from FEAT-144. Three states: member / leader / no-party.
// All existing actions preserved: create / invite / respond / leave /
// disband / rename / avatar upload.
import { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { Trash2, Users } from 'lucide-react';
import { useAppSelector } from '../../../redux/store';
import {
  Party,
  IncomingInvite,
  PlayerOnLocation,
  getMyParty,
  getIncomingInvites,
  createParty,
  invitePlayer,
  respondInvite,
  leaveParty,
  disbandParty,
  getPlayersOnLocation,
  updateParty,
  uploadSquadAvatar,
} from '../../../api/squads';
import PartyHeaderCard from './PartyHeaderCard';
import PartyMemberCard from './PartyMemberCard';
import InviteFromLocationPanel from './InviteFromLocationPanel';
import PartyInvitesPanel from './PartyInvitesPanel';
import PartyCreateCard from './PartyCreateCard';

const PARTY_MAX_SIZE = 4;

interface PartyTabProps {
  characterId: number;
}

const PartyTab = ({ characterId }: PartyTabProps) => {
  const character = useAppSelector((s) => s.user.character);
  const myLocation =
    (character as { current_location?: { id?: number; name?: string } | null } | null)
      ?.current_location ?? null;
  const myLocationId = myLocation?.id ?? null;
  const myLocationName = myLocation?.name ?? null;

  const [party, setParty] = useState<Party | null>(null);
  const [invites, setInvites] = useState<IncomingInvite[]>([]);
  const [locPlayers, setLocPlayers] = useState<PlayerOnLocation[]>([]);
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isLeader = party?.leader_character_id === characterId;

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [p, inv] = await Promise.all([
        getMyParty(characterId),
        getIncomingInvites(characterId),
      ]);
      setParty(p);
      setInvites(inv);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Не удалось загрузить отряд');
    } finally {
      setLoading(false);
    }
  }, [characterId]);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    if (party && party.leader_character_id === characterId && myLocationId) {
      getPlayersOnLocation(myLocationId)
        .then(setLocPlayers)
        .catch(() => setLocPlayers([]));
    } else {
      setLocPlayers([]);
    }
  }, [party, characterId, myLocationId]);

  const guard = async (fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setBusy(false);
    }
  };

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || !party) return;
    guard(async () => {
      const url = await uploadSquadAvatar(file);
      await updateParty(party.id, { avatar: url });
      toast.success('Аватар отряда обновлён');
      await reload();
    });
  };

  const handleRename = (newName: string) =>
    guard(async () => {
      await updateParty(party!.id, { name: newName });
      toast.success('Название отряда обновлено');
      await reload();
    });

  const handleCreate = () =>
    guard(async () => {
      if (!name.trim()) {
        toast.error('Введите название отряда');
        return;
      }
      await createParty(characterId, name.trim());
      setName('');
      toast.success('Отряд создан');
      await reload();
    });

  const handleInvite = (cid: number) =>
    guard(async () => {
      await invitePlayer(party!.id, cid);
      toast.success('Приглашение отправлено');
      await reload();
    });

  const handleRespond = (partyId: number, accept: boolean) =>
    guard(async () => {
      await respondInvite(partyId, characterId, accept);
      toast.success(accept ? 'Вы вступили в отряд' : 'Приглашение отклонено');
      await reload();
    });

  const handleLeave = () =>
    guard(async () => {
      await leaveParty(party!.id, characterId);
      toast.success('Вы покинули отряд');
      await reload();
    });

  const handleDisband = () =>
    guard(async () => {
      if (!window.confirm('Распустить отряд? Это действие необратимо.')) return;
      await disbandParty(party!.id);
      toast.success('Отряд распущен');
      await reload();
    });

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="w-7 h-7 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const memberIds = new Set((party?.members ?? []).map((m) => m.character_id));
  const invitable = locPlayers.filter((p) => p.id !== characterId && !memberIds.has(p.id));
  const freeSlots = party ? Math.max(0, PARTY_MAX_SIZE - party.members.length) : 0;
  // Invites can arrive while already in a party — keep the panel visible then.
  const showInvitesPanel = !party || invites.length > 0;
  const hasRightColumn = isLeader || showInvitesPanel;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col gap-4"
    >
      {/* Hidden file input for the squad avatar (leader only) */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleAvatarChange}
      />

      {/* Header row */}
      <div className="flex items-center gap-3.5">
        <h3 className="gold-text text-sm font-medium uppercase tracking-[0.12em]">Отряд</h3>
        {party && (
          <span className="font-mono tabular-nums text-[13px] text-white/50">
            {party.members.filter((m) => m.status === 'accepted').length}/{PARTY_MAX_SIZE}
          </span>
        )}
      </div>

      <div
        className={
          hasRightColumn
            ? 'grid gap-4 items-start lg:grid-cols-[1.15fr_0.85fr]'
            : 'flex flex-col gap-4'
        }
      >
        {/* Left column */}
        {party ? (
          <section className="flex flex-col gap-4 min-w-0">
            <PartyHeaderCard
              party={party}
              isLeader={isLeader}
              busy={busy}
              onAvatarClick={() => fileInputRef.current?.click()}
              onRename={handleRename}
            />

            {/* Member grid + free-slot placeholders */}
            <motion.div
              initial="hidden"
              animate="visible"
              variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.05 } } }}
              className="grid grid-cols-1 sm:grid-cols-2 gap-3.5"
            >
              {party.members.map((m) => (
                <motion.div
                  key={m.character_id}
                  variants={{
                    hidden: { opacity: 0, y: 10 },
                    visible: { opacity: 1, y: 0 },
                  }}
                >
                  <PartyMemberCard member={m} ownLocationId={myLocationId} />
                </motion.div>
              ))}
              {Array.from({ length: freeSlots }, (_, i) => (
                <motion.div
                  key={`free-${i}`}
                  variants={{
                    hidden: { opacity: 0, y: 10 },
                    visible: { opacity: 1, y: 0 },
                  }}
                  className="flex flex-col items-center justify-center gap-2 min-h-[104px] rounded-card border-[1.5px] border-dashed border-gold/[0.18] bg-white/[0.02] text-gold/45"
                >
                  <Users size={22} strokeWidth={1.7} />
                  <span className="text-[11px] uppercase tracking-[0.05em]">Свободный слот</span>
                </motion.div>
              ))}
            </motion.div>

            {isLeader ? (
              <button
                type="button"
                disabled={busy}
                onClick={handleDisband}
                className="self-start flex items-center gap-2 px-[18px] py-2.5 rounded-[10px] text-xs font-medium uppercase tracking-[0.04em] text-site-red/85 bg-site-red/[0.08] border border-site-red/35 cursor-pointer hover:bg-site-red/[0.18] transition-colors duration-200 ease-site disabled:opacity-50"
              >
                <Trash2 size={15} strokeWidth={2} className="shrink-0" />
                Распустить отряд
              </button>
            ) : (
              <button
                type="button"
                disabled={busy}
                onClick={handleLeave}
                className="self-start px-[18px] py-2.5 rounded-[10px] text-xs font-medium uppercase tracking-[0.04em] text-white/70 border border-white/15 cursor-pointer hover:text-site-red hover:border-site-red/40 transition-colors duration-200 ease-site disabled:opacity-50"
              >
                Покинуть отряд
              </button>
            )}
          </section>
        ) : (
          <PartyCreateCard
            name={name}
            onNameChange={setName}
            busy={busy}
            onCreate={handleCreate}
          />
        )}

        {/* Right column */}
        {hasRightColumn && (
          <div className="flex flex-col gap-4 min-w-0">
            {isLeader && (
              <InviteFromLocationPanel
                locationName={myLocationName}
                hasLocation={myLocationId != null}
                players={invitable}
                busy={busy}
                onInvite={handleInvite}
              />
            )}
            {showInvitesPanel && (
              <PartyInvitesPanel invites={invites} busy={busy} onRespond={handleRespond} />
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
};

export default PartyTab;
