import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ArrowLeft, DoorClosed, Landmark, Lock, Settings2, Home } from 'lucide-react';
import {
  enterHouse,
  getHouse,
  goToRoom,
  leaveHouse,
  SEIZED_HOUSE_DETAIL,
  type HouseRoom,
  type HouseView,
} from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { getMe } from '../../../redux/slices/userSlice';
import CharAvatar from './CharAvatar';
import HouseBuffChips from './HouseBuffs';
import HouseFacade from './HouseFacade';
import HouseManage, { canManage } from './HouseManage';
import HouseRoomView from './HouseRoomView';
import HouseTaxPanel from './HouseTaxPanel';

/*
  A player house (FEAT-180). Stage 7: inside, the house is a set of locations —
  `/houses/:id` shows the room the acting character stands in (or the entrance
  with «Войти в дом»), `/houses/:id/room/:roomId` a given room, and
  `/houses/:id/manage` the separate «Управление домом» tab. Outsiders see the
  facade only. The viewer may act through several characters (owner, resident,
  guest); a switcher picks which one.
*/

interface HousePageProps {
  /** The «Управление домом» tab (`/houses/:id/manage`). */
  manage?: boolean;
}

const HousePage = ({ manage = false }: HousePageProps) => {
  const { houseId, roomId } = useParams();
  const id = Number(houseId);
  const urlRoomId = roomId != null ? Number(roomId) : null;
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const currentCharacterId = useAppSelector((state) => state.user.character?.id ?? null);
  // A sleep/reading lock ended elsewhere (the site banner) — reload the house state.
  const lockReason = useAppSelector((state) => (state.user.character?.activity_lock as { reason?: string | null } | undefined)?.reason ?? null);
  const [house, setHouse] = useState<HouseView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actingId, setActingId] = useState<number | null>(null);
  const [movingRoomId, setMovingRoomId] = useState<number | null>(null);
  const [entering, setEntering] = useState(false);
  const [leaving, setLeaving] = useState(false);

  const load = useCallback(() => {
    getHouse(id)
      .then((h) => {
        setHouse(h);
        setError(null);
        if (!h.can_view_inside) return;
        const ids = h.acting.map((a) => a.character?.id).filter((x): x is number => x != null);
        setActingId((cur) => {
          if (cur != null && ids.includes(cur)) return cur;
          if (currentCharacterId != null && ids.includes(currentCharacterId)) return currentCharacterId;
          return ids[0] ?? null;
        });
      })
      .catch((e) => setError(apiErrorMessage(e, 'Не удалось загрузить дом')));
  }, [id, currentCharacterId]);

  useEffect(load, [load, lockReason]);

  const inside = house && house.can_view_inside ? house : null;
  const acting = useMemo(
    () => inside?.acting.find((a) => a.character?.id === actingId) ?? null,
    [inside, actingId],
  );

  const move = async (room: HouseRoom) => {
    const character = acting?.character;
    if (!character) return;
    setMovingRoomId(room.id);
    try {
      await goToRoom(room.id, character.id);
      navigate(`/houses/${id}/room/${room.id}`);
      load();
      void dispatch(getMe()); // the header's «back to the house» link
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось перейти в комнату'));
    } finally {
      setMovingRoomId(null);
    }
  };

  const enter = async () => {
    const character = acting?.character;
    if (!character) return;
    setEntering(true);
    try {
      const r = await enterHouse(id, character.id);
      if (r.room_id != null) navigate(`/houses/${id}/room/${r.room_id}`);
      load();
      void dispatch(getMe());
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось войти в дом'));
    } finally {
      setEntering(false);
    }
  };

  const leave = async () => {
    const character = acting?.character;
    if (!character || !inside) return;
    setLeaving(true);
    try {
      await leaveHouse(id, character.id);
      toast.success(`${character.name} выходит из дома`);
      void dispatch(getMe());
      navigate(`/location/${inside.location_id}`);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось выйти из дома'));
    } finally {
      setLeaving(false);
    }
  };

  if (error === SEIZED_HOUSE_DETAIL) {
    return (
      <div className="w-full max-w-container mx-auto flex flex-col items-start gap-4">
        <Link to="/houses" className="text-white/60 hover:text-white text-sm flex items-center gap-1"><ArrowLeft size={15} />Мои дома</Link>
        <div className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 p-6 flex items-start gap-3 max-w-2xl">
          <Landmark size={22} className="text-gold shrink-0 mt-0.5" />
          <div className="flex flex-col gap-2">
            <h1 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Дом изъят городом</h1>
            <p className="text-white/70 text-sm leading-relaxed">
              Этого дома больше нет: город забрал его за неуплату налога или потому, что хозяин ушёл, не оставив наследника.
              Участок снова продаётся — его можно найти на странице локации.
            </p>
            <Link to="/houses/market" className="site-link text-sm self-start">Доска продажи домов</Link>
          </div>
        </div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="w-full max-w-container mx-auto flex flex-col items-start gap-4">
        <Link to="/houses" className="text-white/60 hover:text-white text-sm flex items-center gap-1"><ArrowLeft size={15} />Мои дома</Link>
        <div className="bg-site-bg backdrop-blur-sm rounded-card border border-white/10 p-6 text-white/80 flex items-center gap-3">
          <Lock size={18} className="text-gold shrink-0" />{error}
        </div>
      </div>
    );
  }
  if (!house) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin mx-auto" />;

  if (house.can_view_inside === false) {
    if (urlRoomId != null || manage) {
      return (
        <div className="w-full max-w-container mx-auto flex flex-col items-start gap-4">
          <Link to={`/houses/${house.id}`} className="text-white/60 hover:text-white text-sm flex items-center gap-1 min-w-0">
            <ArrowLeft size={15} className="shrink-0" /><span className="truncate">{house.name}</span>
          </Link>
          <div className="bg-site-bg backdrop-blur-sm rounded-card border border-white/10 p-6 text-white/80 flex items-center gap-3">
            <Lock size={18} className="text-gold shrink-0" />Внутрь дома могут заглянуть только хозяин, жильцы и гости.
          </div>
        </div>
      );
    }
    return <HouseFacade house={house} onChanged={load} />;
  }

  const h = house;
  const manageable = canManage(h);
  const showManage = manage && manageable;
  const viewedRoomId = urlRoomId ?? acting?.room_id ?? null;
  const viewedRoom = viewedRoomId != null ? h.rooms.find((r) => r.id === viewedRoomId) ?? null : null;
  const roomMissing = viewedRoomId != null && viewedRoom == null;
  const members = h.acting.filter((a) => !a.is_guest);
  const taxAlert = h.status === 'frozen' || (h.tax?.owed_periods ?? 0) > 0;
  const actingRole = (a: (typeof h.acting)[number]) => (a.is_owner ? 'хозяин' : a.is_guest ? 'гость' : 'жилец');
  const roomLink = acting?.room_id != null ? `/houses/${h.id}/room/${acting.room_id}` : `/houses/${h.id}`;

  const characterBar = (
    <>
      {h.acting.length > 1 && (
        <div className="flex items-center gap-2 flex-wrap pt-1">
          <span className="text-white/50 text-xs uppercase tracking-[0.06em] mr-1">Действует</span>
          {h.acting.map((a) => a.character && (
            <button key={a.character.id} type="button" onClick={() => setActingId(a.character!.id)}
              className={`flex items-center gap-2 pl-1 pr-3 py-1 rounded-full border text-sm transition-colors max-w-full ${
                a.character.id === actingId ? 'border-gold/70 text-gold bg-gold/10' : 'border-white/10 text-white/60 hover:text-white'
              }`}>
              <CharAvatar src={a.character.avatar} size="w-6 h-6" />
              <span className="truncate max-w-[120px] sm:max-w-[140px]">{a.character.name}</span>
              <span className="text-[10px] text-white/40">{actingRole(a)}</span>
            </button>
          ))}
        </div>
      )}
      {acting?.character && (
        <HouseBuffChips buffs={acting.buffs ?? []} trophyBonus={acting.trophy_bonus ?? 0} className="pt-1" />
      )}
      {acting?.is_guest && h.acting.length === 1 && (
        <span className="self-start px-2 py-0.5 rounded-full border border-site-blue/50 text-site-blue text-[11px]">
          {acting.character?.name} — гость: доступны гостевые комнаты
        </span>
      )}
    </>
  );

  const tabClass = (active: boolean) => `flex items-center gap-1.5 min-w-0 px-3 py-2 rounded-card text-xs sm:text-sm uppercase tracking-[0.06em] whitespace-nowrap transition-colors duration-200 ease-site ${
    active ? 'bg-gold/10 text-gold border border-gold/40' : 'border border-transparent text-white/55 hover:text-white hover:bg-white/[0.06]'
  }`;

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-4 sm:gap-5 pb-10">
      {/* One dark bar: back to the location · house tabs · leave */}
      <nav className="flex items-center gap-2 sm:gap-3 flex-wrap p-1.5 sm:p-2 rounded-card bg-site-bg backdrop-blur-sm border border-white/10 shadow-card">
        <Link to={`/location/${h.location_id}`} title="К локации"
          className="flex items-center gap-1.5 min-w-0 max-w-[45%] sm:max-w-[220px] px-3 py-2 rounded-card text-white/70 hover:text-white hover:bg-white/[0.06] text-sm transition-colors duration-200 ease-site">
          <ArrowLeft size={15} className="shrink-0" /><span className="truncate">{h.location_name ?? 'К локации'}</span>
        </Link>
        {manageable && (
          <>
            <span className="hidden sm:block w-px h-6 bg-white/10 shrink-0" aria-hidden="true" />
            <div className="flex items-center gap-1 min-w-0">
              <Link to={roomLink} className={tabClass(!showManage)}>
                <Home size={14} className="shrink-0" /><span className="truncate">{acting?.room_id != null ? 'В доме' : 'Дом'}</span>
              </Link>
              <Link to={`/houses/${h.id}/manage`} className={tabClass(showManage)}>
                <Settings2 size={14} className="shrink-0" /><span className="truncate">Управление<span className="hidden sm:inline"> домом</span></span>
              </Link>
            </div>
          </>
        )}
        {acting?.character && acting.room_id != null && (
          <button type="button" onClick={() => void leave()} disabled={leaving}
            className="ml-auto flex items-center gap-1.5 shrink-0 px-3.5 py-2 rounded-card border border-white/10 text-white/70 hover:text-site-red hover:border-site-red/50 text-xs sm:text-sm uppercase tracking-[0.06em] transition-colors duration-200 ease-site disabled:opacity-50">
            <DoorClosed size={14} className="shrink-0" />{leaving ? 'Выходим...' : 'Выйти из дома'}
          </button>
        )}
      </nav>

      {!showManage && taxAlert && members.length > 0 && (
        <HouseTaxPanel house={h} acting={acting && !acting.is_guest ? acting : members[0]} onChanged={load} />
      )}

      {showManage ? (
        <HouseManage house={h} acting={acting} onChanged={load} />
      ) : roomMissing ? (
        <div className="bg-site-bg backdrop-blur-sm rounded-card border border-white/10 p-6 text-white/80 flex items-center gap-3">
          <Lock size={18} className="text-gold shrink-0" />Комната не найдена — возможно, её снесли.
          <Link to={`/houses/${h.id}`} className="site-link ml-auto shrink-0">К дому</Link>
        </div>
      ) : (
        <HouseRoomView house={h} acting={acting} room={viewedRoom} characterBar={characterBar}
          movingRoomId={movingRoomId} entering={entering}
          onMove={(room) => void move(room)} onEnter={() => void enter()} onChanged={load} />
      )}
    </div>
  );
};

export default HousePage;
