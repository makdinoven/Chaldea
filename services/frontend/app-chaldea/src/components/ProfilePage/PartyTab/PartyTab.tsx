import { useCallback, useEffect, useState } from "react";
import toast from "react-hot-toast";
import { useAppSelector } from "../../../redux/store";
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
} from "../../../api/squads";

interface PartyTabProps {
  characterId: number;
}

const PartyTab = ({ characterId }: PartyTabProps) => {
  const character = useAppSelector((s) => s.user.character);
  const myLocationId =
    (character as { current_location?: { id?: number } } | null)?.current_location?.id ?? null;

  const [party, setParty] = useState<Party | null>(null);
  const [invites, setInvites] = useState<IncomingInvite[]>([]);
  const [locPlayers, setLocPlayers] = useState<PlayerOnLocation[]>([]);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

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
      toast.error(e instanceof Error ? e.message : "Не удалось загрузить отряд");
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
      toast.error(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBusy(false);
    }
  };

  const handleCreate = () =>
    guard(async () => {
      if (!name.trim()) {
        toast.error("Введите название отряда");
        return;
      }
      await createParty(characterId, name.trim());
      setName("");
      toast.success("Отряд создан");
      await reload();
    });

  const handleInvite = (cid: number) =>
    guard(async () => {
      await invitePlayer(party!.id, cid);
      toast.success("Приглашение отправлено");
      await reload();
    });

  const handleRespond = (partyId: number, accept: boolean) =>
    guard(async () => {
      await respondInvite(partyId, characterId, accept);
      toast.success(accept ? "Вы вступили в отряд" : "Приглашение отклонено");
      await reload();
    });

  const handleLeave = () =>
    guard(async () => {
      await leaveParty(party!.id, characterId);
      toast.success("Вы покинули отряд");
      await reload();
    });

  const handleDisband = () =>
    guard(async () => {
      if (!window.confirm("Распустить отряд? Это действие необратимо.")) return;
      await disbandParty(party!.id);
      toast.success("Отряд распущен");
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
  const invitable = locPlayers.filter(
    (p) => p.id !== characterId && !memberIds.has(p.id),
  );

  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-6">
      {/* Incoming invites */}
      {invites.length > 0 && (
        <section className="flex flex-col gap-3">
          <h3 className="gold-text text-lg font-medium uppercase">Приглашения</h3>
          {invites.map((inv) => (
            <div
              key={inv.party_id}
              className="flex items-center justify-between gap-3 bg-white/[0.03] rounded-lg p-3"
            >
              <div className="min-w-0">
                <p className="text-white truncate">{inv.party_name}</p>
                <p className="text-white/50 text-xs truncate">
                  Лидер: {inv.leader_name ?? `#${inv.leader_character_id}`}
                </p>
              </div>
              <div className="flex gap-2 shrink-0">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => handleRespond(inv.party_id, true)}
                  className="px-3 py-1.5 rounded-lg border border-emerald-400/40 text-emerald-300 text-sm hover:bg-emerald-400/10 transition disabled:opacity-50"
                >
                  Принять
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => handleRespond(inv.party_id, false)}
                  className="px-3 py-1.5 rounded-lg border border-white/15 text-white/60 text-sm hover:bg-white/5 transition disabled:opacity-50"
                >
                  Отклонить
                </button>
              </div>
            </div>
          ))}
        </section>
      )}

      {/* No party yet — create form */}
      {!party && (
        <section className="flex flex-col gap-4 bg-white/[0.03] rounded-lg p-5">
          <h3 className="gold-text text-lg font-medium uppercase">Создать отряд</h3>
          <p className="text-white/50 text-sm">
            Постоянный отряд: до 4 участников, совместные бои, данжи и бонус к опыту
            рядом с соотрядцами. Приглашать можно только игроков на вашей локации.
          </p>
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="text"
              value={name}
              maxLength={60}
              onChange={(e) => setName(e.target.value)}
              placeholder="Название отряда"
              className="flex-1 bg-transparent border-b border-white/20 focus:border-gold outline-none py-2 text-white placeholder-white/30 transition"
            />
            <button
              type="button"
              disabled={busy}
              onClick={handleCreate}
              className="px-5 py-2 rounded-lg border border-gold/40 text-gold hover:bg-gold/10 transition disabled:opacity-50 whitespace-nowrap"
            >
              Создать
            </button>
          </div>
        </section>
      )}

      {/* Party card */}
      {party && (
        <section className="flex flex-col gap-5">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-lg bg-white/5 border border-gold/20 flex items-center justify-center overflow-hidden shrink-0">
              {party.avatar ? (
                <img src={party.avatar} alt="" className="w-full h-full object-cover" />
              ) : (
                <span className="text-gold text-xl">⚔</span>
              )}
            </div>
            <div className="min-w-0">
              <h3 className="gold-text text-xl font-medium truncate">{party.name}</h3>
              <p className="text-white/50 text-xs">
                {party.members.filter((m) => m.status === "accepted").length} / 4 в отряде
              </p>
            </div>
          </div>

          {/* Members */}
          <div className="flex flex-col gap-2">
            {party.members.map((m) => {
              const green = m.current_location_id != null && m.current_location_id === myLocationId;
              return (
                <div
                  key={m.character_id}
                  className="flex items-center gap-3 bg-white/[0.03] rounded-lg p-3"
                >
                  <span
                    className={`inline-block w-2.5 h-2.5 rounded-full shrink-0 ${
                      green ? "bg-emerald-400" : "bg-red-500/70"
                    }`}
                    title={green ? "На вашей локации" : "В другой локации"}
                  />
                  <div className="w-8 h-8 rounded-full bg-white/10 overflow-hidden shrink-0">
                    {m.avatar && <img src={m.avatar} alt="" className="w-full h-full object-cover" />}
                  </div>
                  <span className="text-white flex-1 min-w-0 truncate">
                    {m.name ?? `#${m.character_id}`}
                  </span>
                  {m.is_leader && (
                    <span className="text-gold text-xs uppercase tracking-wide shrink-0">Лидер</span>
                  )}
                  {m.status === "invited" && (
                    <span className="text-white/40 text-xs shrink-0">приглашён…</span>
                  )}
                </div>
              );
            })}
          </div>

          {/* Leader: invite players on this location */}
          {isLeader && (
            <div className="flex flex-col gap-2">
              <h4 className="text-white/70 text-sm uppercase tracking-wide">
                Пригласить с локации
              </h4>
              {!myLocationId ? (
                <p className="text-white/40 text-sm">Вы не находитесь в локации.</p>
              ) : invitable.length === 0 ? (
                <p className="text-white/40 text-sm">Нет доступных игроков на вашей локации.</p>
              ) : (
                invitable.map((p) => (
                  <div
                    key={p.id}
                    className="flex items-center gap-3 bg-white/[0.02] rounded-lg p-2.5"
                  >
                    <div className="w-8 h-8 rounded-full bg-white/10 overflow-hidden shrink-0">
                      {p.avatar && <img src={p.avatar} alt="" className="w-full h-full object-cover" />}
                    </div>
                    <span className="text-white/90 flex-1 min-w-0 truncate">{p.name}</span>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => handleInvite(p.id)}
                      className="px-3 py-1.5 rounded-lg border border-gold/40 text-gold text-sm hover:bg-gold/10 transition disabled:opacity-50 shrink-0"
                    >
                      Пригласить
                    </button>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Controls */}
          <div className="flex gap-3 pt-2">
            {isLeader ? (
              <button
                type="button"
                disabled={busy}
                onClick={handleDisband}
                className="px-4 py-2 rounded-lg border border-red-500/40 text-red-300 text-sm hover:bg-red-500/10 transition disabled:opacity-50"
              >
                Распустить отряд
              </button>
            ) : (
              <button
                type="button"
                disabled={busy}
                onClick={handleLeave}
                className="px-4 py-2 rounded-lg border border-white/15 text-white/70 text-sm hover:bg-white/5 transition disabled:opacity-50"
              >
                Покинуть отряд
              </button>
            )}
          </div>
        </section>
      )}
    </div>
  );
};

export default PartyTab;
