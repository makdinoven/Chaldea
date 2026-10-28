import { useNavigate } from 'react-router-dom';
import { ChevronRight, DoorOpen, Footprints, Hammer, Lock, Users } from 'lucide-react';
import { ROOM_TYPE_LABEL, type ActingCharacter, type House, type HouseRoom } from '../../../api/houses';
import { ROOM_TYPE_ICON } from './building';

/*
  FEAT-180 stage 7 — «Комнаты дома»: the house's counterpart of the location
  page's «Соседние локации» panel. Each row opens the room; «Перейти» moves the
  acting character there at once (free, instant, no post).
*/

interface HouseRoomsPanelProps {
  house: House;
  acting: ActingCharacter | null;
  /** The room shown on the page now (null — the entrance). */
  viewedRoomId: number | null;
  /** A move request is running for this room. */
  movingRoomId: number | null;
  onMove: (room: HouseRoom) => void;
}

/** Whether the room is let to the acting character (guests: guest rooms; residents: their rooms). */
const isLetIn = (room: HouseRoom, acting: ActingCharacter | null) => acting != null && acting.room_ids.includes(room.id);

const HouseRoomsPanel = ({ house, acting, viewedRoomId, movingRoomId, onMove }: HouseRoomsPanelProps) => {
  const navigate = useNavigate();
  const rooms = house.rooms;
  const standingIn = acting?.room_id ?? null;

  return (
    <aside className="w-full lg:w-[330px] lg:shrink-0 lg:self-stretch flex flex-col min-h-0 overflow-hidden rounded-card bg-site-bg backdrop-blur-sm border border-gold-dark/20 shadow-card">
      <div className="flex items-center gap-2.5 px-4 py-3.5 border-b border-white/[0.07] shrink-0">
        <DoorOpen size={18} className="text-gold shrink-0" />
        <h2 className="gold-text text-[13px] font-medium uppercase tracking-[0.08em]">Комнаты дома</h2>
        {rooms.length > 0 && (
          <span className="ml-auto bg-white/10 text-white/60 text-[10px] font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center shrink-0">
            {rooms.length}
          </span>
        )}
      </div>

      {rooms.length === 0 ? (
        <p className="flex-1 min-h-0 flex items-center justify-center p-5 text-white/50 text-sm text-center">
          {house.plot_kind === 'empty' ? 'Комнат пока нет — хозяин строит их во вкладке «Управление домом».' : 'Комнат пока нет'}
        </p>
      ) : (
        <div className="flex-1 min-h-0 flex flex-col gap-2 p-3 max-h-[300px] lg:max-h-none overflow-y-auto gold-scrollbar">
          {rooms.map((room) => {
            const Icon = ROOM_TYPE_ICON[room.room_type];
            const built = room.level >= 1;
            const letIn = isLetIn(room, acting);
            const viewed = room.id === viewedRoomId;
            const here = room.id === standingIn;
            const present = room.present ?? [];
            const canMove = acting?.character != null && letIn && built && !here;
            return (
              <div key={room.id}
                className={`group flex items-center gap-3 p-2 shrink-0 rounded-card border transition-all duration-200 ease-site ${
                  viewed ? 'bg-gold/[0.07] border-gold-dark/60' : 'bg-white/[0.03] border-white/[0.06] hover:border-gold-dark/40 hover:bg-white/[0.06]'
                }`}>
                <button type="button" disabled={!room.can_read || !built}
                  onClick={() => navigate(`/houses/${house.id}/room/${room.id}`)}
                  title={!room.can_read ? 'Вас не впускали в эту комнату' : !built ? 'Комната ещё строится' : `Открыть: ${room.name}`}
                  className="flex items-center gap-3 flex-1 min-w-0 text-left disabled:cursor-default">
                  <span className="relative w-12 h-12 shrink-0 rounded-[10px] overflow-hidden bg-black/40 flex items-center justify-center">
                    {room.image_url ? (
                      <img src={room.image_url} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <Icon size={20} className="text-gold/80" />
                    )}
                    {!letIn && (
                      <span className="absolute inset-0 bg-black/55 flex items-center justify-center">
                        <Lock size={15} className="text-white/70" />
                      </span>
                    )}
                  </span>
                  <span className="flex-1 min-w-0 flex flex-col gap-1">
                    <span className={`text-[13px] font-medium truncate ${viewed ? 'text-gold-light' : 'text-white'}`}>{room.name}</span>
                    <span className="flex items-center gap-x-2.5 gap-y-0.5 flex-wrap text-[11px]">
                      <span className="text-white/50 truncate">{ROOM_TYPE_LABEL[room.room_type]}{built ? ` · ур. ${room.level}` : ''}</span>
                      {!built && <span className="flex items-center gap-1 text-gold-light"><Hammer size={11} />строится</span>}
                      {present.length > 0 && (
                        <span className="flex items-center gap-1 text-stat-energy" title={present.map((p) => p.name).join(', ')}>
                          <Users size={11} />{present.length}
                        </span>
                      )}
                      {here && <span className="text-site-blue">вы здесь</span>}
                    </span>
                  </span>
                </button>
                {canMove ? (
                  <button type="button" onClick={() => onMove(room)} disabled={movingRoomId != null}
                    className="shrink-0 flex items-center gap-1 px-2.5 py-1.5 rounded-[9px] border border-site-blue/40 text-site-blue text-[11px] font-medium hover:bg-site-blue/15 transition-colors duration-200 ease-site disabled:opacity-50">
                    <Footprints size={12} />{movingRoomId === room.id ? '...' : 'Перейти'}
                  </button>
                ) : (
                  room.can_read && built && !here && (
                    <ChevronRight size={15} className="shrink-0 text-white/35 group-hover:text-site-blue transition-colors duration-200 ease-site" />
                  )
                )}
              </div>
            );
          })}
        </div>
      )}
    </aside>
  );
};

export default HouseRoomsPanel;
