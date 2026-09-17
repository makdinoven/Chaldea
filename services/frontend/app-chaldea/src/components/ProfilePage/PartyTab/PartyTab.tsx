// ProfilePage PartyTab — redesigned per Claude Design mock (FEAT-151),
// party system from FEAT-144, moved into PanelShells (FEAT-166).
// Three states: member / leader / no-party.
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
import PanelShell, { PANEL_DESKTOP_HEIGHT_CLASS } from '../PanelShell';
import LoadingState from '../shared/LoadingState';
import PanelCounter from '../shared/PanelCounter';
import SectionHeader from '../shared/SectionHeader';

const PARTY_MAX_SIZE = 4;
/** Each right-column panel gets half the desktop height when both are shown */
const HALF_PANEL_DESKTOP_MAX_HEIGHT_CLASS = 'lg:max-h-[calc((100vh-150px)/2)]';

const tabMotion = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.3, ease: 'easeOut' },
} as const;

const partyIcon = <Users size={18} strokeWidth={1.8} className="text-gold shrink-0" />;

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
      <motion.div {...tabMotion}>
        <PanelShell title="Отряд" icon={partyIcon}>
          <LoadingState />
        </PanelShell>
      </motion.div>
    );
  }

  const memberIds = new Set((party?.members ?? []).map((m) => m.character_id));
  const invitable = locPlayers.filter((p) => p.id !== characterId && !memberIds.has(p.id));
  const freeSlots = party ? Math.max(0, PARTY_MAX_SIZE - party.members.length) : 0;
  // Invites can arrive while already in a party — keep the panel visible then.
  const showInvitesPanel = !party || invites.length > 0;
  const hasRightColumn = isLeader || showInvitesPanel;
  const bothRightPanels = isLeader && showInvitesPanel;

  // Hidden file input for the squad avatar (leader only)
  const avatarInput = (
    <input
      ref={fileInputRef}
      type="file"
      accept="image/*"
      className="hidden"
      onChange={handleAvatarChange}
    />
  );

  if (!party) {
    return (
      <motion.div {...tabMotion}>
        {avatarInput}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-start">
          <PartyCreateCard
            name={name}
            onNameChange={setName}
            busy={busy}
            onCreate={handleCreate}
          />
          <PartyInvitesPanel invites={invites} busy={busy} onRespond={handleRespond} />
        </div>
      </motion.div>
    );
  }

  const acceptedCount = party.members.filter((m) => m.status === 'accepted').length;

  return (
    <motion.div {...tabMotion}>
      {avatarInput}

      <div
        className={`grid grid-cols-1 gap-5 items-start ${
          hasRightColumn ? 'lg:grid-cols-[1fr_392px]' : ''
        }`}
      >
        {/* Left panel: identity band, members, actions */}
        <PanelShell
          title="Отряд"
          icon={partyIcon}
          headerExtra={
            <PanelCounter>
              {acceptedCount}/{PARTY_MAX_SIZE}
            </PanelCounter>
          }
          className={PANEL_DESKTOP_HEIGHT_CLASS}
        >
          <div className="flex flex-col gap-6">
            <PartyHeaderCard
              party={party}
              isLeader={isLeader}
              busy={busy}
              onAvatarClick={() => fileInputRef.current?.click()}
              onRename={handleRename}
            />

            <div className="flex flex-col gap-3.5">
              <SectionHeader title="Участники" />

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
                    className="flex flex-col items-center justify-center gap-2 min-h-[104px] rounded-card border-[1.5px] border-dashed border-white/15 text-white/35"
                  >
                    <Users size={22} strokeWidth={1.7} />
                    <span className="text-[11px] uppercase tracking-[0.05em]">Свободный слот</span>
                  </motion.div>
                ))}
              </motion.div>
            </div>

            {isLeader ? (
              <button
                type="button"
                disabled={busy}
                onClick={handleDisband}
                className="w-full sm:w-auto sm:self-start flex items-center justify-center gap-2 px-[18px] py-2.5 rounded-[10px] text-xs font-medium uppercase tracking-[0.04em] text-site-red/85 bg-site-red/[0.08] border border-site-red/35 cursor-pointer hover:bg-site-red/[0.18] transition-colors duration-200 ease-site disabled:opacity-50"
              >
                <Trash2 size={15} strokeWidth={2} className="shrink-0" />
                Распустить отряд
              </button>
            ) : (
              <button
                type="button"
                disabled={busy}
                onClick={handleLeave}
                className="w-full sm:w-auto sm:self-start px-[18px] py-2.5 rounded-[10px] text-xs font-medium uppercase tracking-[0.04em] text-white/70 border border-white/15 cursor-pointer hover:text-site-red hover:border-site-red/40 transition-colors duration-200 ease-site disabled:opacity-50"
              >
                Покинуть отряд
              </button>
            )}
          </div>
        </PanelShell>

        {/* Right column */}
        {hasRightColumn && (
          <div className="flex flex-col gap-5 min-w-0">
            {isLeader && (
              <InviteFromLocationPanel
                locationName={myLocationName}
                hasLocation={myLocationId != null}
                players={invitable}
                busy={busy}
                onInvite={handleInvite}
                className={
                  bothRightPanels ? HALF_PANEL_DESKTOP_MAX_HEIGHT_CLASS : PANEL_DESKTOP_HEIGHT_CLASS
                }
              />
            )}
            {showInvitesPanel && (
              <PartyInvitesPanel
                invites={invites}
                busy={busy}
                onRespond={handleRespond}
                className={bothRightPanels ? HALF_PANEL_DESKTOP_MAX_HEIGHT_CLASS : ''}
              />
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
};

export default PartyTab;
