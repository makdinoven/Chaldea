import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  Armchair,
  Bath,
  BedDouble,
  BookOpen,
  DoorOpen,
  Flame,
  Footprints,
  Hammer,
  Home,
  Lock,
  MapPin,
  MessageSquare,
  Orbit,
  Package,
  ShieldCheck,
  Sprout,
  Trophy,
  Users,
  type LucideIcon,
} from 'lucide-react';
import {
  isGardenRoom,
  isProfessionRoom,
  isSleepRoom,
  KITCHEN_SATIETY_HOURS_BY_LEVEL,
  PROFESSION_NAME_BY_SLUG,
  ROOM_TYPE_LABEL,
  roomProfessionName,
  STORAGE_ROOMS,
  type ActingCharacter,
  type House,
  type HouseChar,
  type HouseRoom,
} from '../../../api/houses';
import { useBodyBackground } from '../../../hooks/useBodyBackground';
import { cellsWord, furnitureBonusText } from '../../../utils/furniture';
import CharAvatar from './CharAvatar';
import { FurnitureIcon } from './FurnitureIcon';
import SleepControl from './SleepControl';
import { BathControl, GardenBeds, roomInfoContent } from './RoomFeatures';
import { LibraryControl, ReturnCircleInfo, ShrineControl } from './RoomBlessings';
import TrophyHall from './TrophyHall';
import StorageControl from './HouseStorage';
import HouseRoomsPanel from './HouseRoomsPanel';
import { ACTION_BAR } from './RoomAction';
import { InfoTooltip, WithTooltip } from '../../CommonComponents/InfoTooltip';
import RoomPosts from './RoomPosts';
import { bedsWord, BuildStatus, levelPerk, ROOM_TYPE_ICON } from './building';

/*
  FEAT-180 stage 7 — a house seen from inside, laid out like a location page:
  the room hero with «Комнаты дома» on the side (quick moves), who stands here,
  what the room can do, and its posts. Without a room (the character is
  outside) it is the house's entrance with «Войти в дом».
*/

interface HouseRoomViewProps {
  house: House;
  acting: ActingCharacter | null;
  /** The room on screen; null — the entrance (the acting character is outside). */
  room: HouseRoom | null;
  /** Acting-character switcher and buff chips, shown in the hero. */
  characterBar: ReactNode;
  movingRoomId: number | null;
  entering: boolean;
  onMove: (room: HouseRoom) => void;
  onEnter: () => void;
  onChanged: () => void;
}

interface Chip {
  icon: LucideIcon;
  text: string;
}

const fmt = (n: number) => n.toLocaleString('ru-RU', { maximumFractionDigits: 1 });

/** «Что здесь можно делать» — short chips of the room's functions for the hero. */
const functionChips = (room: HouseRoom): Chip[] => {
  const chips: Chip[] = [];
  if (room.level < 1) return [{ icon: Hammer, text: 'Строится — функции заработают после стройки' }];
  const perk = levelPerk(room.room_type, room.level);
  const t = room.room_type;
  if (isSleepRoom(t)) chips.push({ icon: BedDouble, text: `Сон ×${fmt(room.sleep_factor ?? 1)}` });
  if (t === 'bath') chips.push({ icon: Bath, text: `Баня раз в сутки: ${perk ?? ''}` });
  if (isGardenRoom(t)) {
    const n = room.beds_total ?? 0;
    chips.push({ icon: Sprout, text: `${ROOM_TYPE_LABEL[t]}: ${n} ${bedsWord(t, n)}` });
  }
  if (isProfessionRoom(t)) {
    const profession = room.profession_slug
      ? PROFESSION_NAME_BY_SLUG[room.profession_slug] ?? room.profession_slug
      : roomProfessionName(t);
    chips.push({ icon: Hammer, text: `Мастерская: ${profession ?? ROOM_TYPE_LABEL[t]}` });
    if (t === 'kitchen') chips.push({ icon: Flame, text: `Сытость ${KITCHEN_SATIETY_HOURS_BY_LEVEL[room.level] ?? 24} ч` });
  }
  if (STORAGE_ROOMS.includes(t) && room.storage_stacks != null) {
    chips.push({ icon: Package, text: `Хранилище: ${room.storage_stacks} ${cellsWord(room.storage_stacks)}` });
  }
  if (t === 'library') chips.push({ icon: BookOpen, text: `Чтение: ${perk ?? ''}` });
  if (t === 'shrine') chips.push({ icon: Flame, text: `Молитва раз в сутки: ${perk ?? ''}` });
  if (t === 'trophy_hall') chips.push({ icon: Trophy, text: `Трофеи: ${(room.furniture ?? []).length} из ${room.trophy_slots ?? 0}` });
  if (t === 'return_circle') chips.push({ icon: Orbit, text: 'Свиток возвращения ведёт сюда' });
  if (room.furniture_group && t !== 'trophy_hall') {
    chips.push({ icon: Armchair, text: `Мебель: ${(room.furniture ?? []).length} из ${room.furniture_slots ?? room.level}` });
  }
  chips.push({ icon: MessageSquare, text: 'Посты' });
  return chips;
};

const CHIP = 'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-white/15 bg-black/30 text-white/80 text-[11px] leading-tight max-w-full';

/** Avatars of the characters standing somewhere — the look of the location's players list. */
const PresentList = ({ people, note }: { people: (HouseChar & { where?: string })[]; note: string }) => (
  people.length === 0 ? (
    <p className="flex-1 flex items-center justify-center text-white/45 text-sm p-4 text-center">{note}</p>
  ) : (
    <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-3 content-start gap-2 p-3 sm:p-4">
      {people.map((p) => (
        <div key={p.id} className="flex flex-col items-center gap-1.5 p-2 rounded-card hover:bg-white/5 transition-colors duration-200 min-w-0">
          <div className="gold-outline relative w-14 h-14 sm:w-16 sm:h-16 rounded-full overflow-hidden bg-black/40 shrink-0">
            {p.avatar && <img src={p.avatar} alt={p.name} className="w-full h-full object-cover" />}
          </div>
          <span className="text-white text-xs text-center truncate w-full">{p.name}</span>
          {p.where && <span className="text-white/45 text-[10px] text-center truncate w-full">{p.where}</span>}
        </div>
      ))}
    </div>
  )
);

const PANEL = 'bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] overflow-hidden';
const PANEL_HEAD = 'flex items-center gap-2.5 px-4 sm:px-5 py-3.5 border-b border-white/[0.07]';

const HouseRoomView = ({ house, acting, room, characterBar, movingRoomId, entering, onMove, onEnter, onChanged }: HouseRoomViewProps) => {
  useBodyBackground(room?.image_url ?? house.image_url);
  const frozen = house.status === 'frozen';
  const character = acting?.character ?? null;
  const atHouseLocation = acting?.location_id != null && acting.location_id === house.location_id;
  const standingRoom = acting?.room_id != null ? house.rooms.find((r) => r.id === acting.room_id) ?? null : null;

  const panel = (
    <HouseRoomsPanel house={house} acting={acting} viewedRoomId={room?.id ?? null} movingRoomId={movingRoomId} onMove={onMove} />
  );

  // --- The entrance: the acting character is outside the house ---
  if (!room) {
    const inside = house.rooms.flatMap((r) => (r.present ?? []).map((p) => ({ ...p, where: r.name })));
    return (
      <div className="flex flex-col gap-4 sm:gap-5">
        <section className="relative h-auto lg:max-h-[400px] rounded-card overflow-hidden bg-site-bg backdrop-blur-sm border border-gold-dark/20 shadow-card flex flex-col">
          <div className="absolute top-4 left-4 sm:top-5 sm:left-6 flex items-center gap-2.5 flex-wrap">
            <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-[11px] font-medium uppercase tracking-[0.06em] shadow-card bg-green-600/80 text-green-100 border-green-300/40">
              <ShieldCheck size={13} />Безопасная
            </span>
            <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-site-bg border border-gold-dark/60 text-gold text-[11px] font-medium uppercase tracking-[0.06em]">
              <Home size={12} />Дом
            </span>
          </div>
          <div className="relative flex-1 min-h-0 flex flex-col lg:flex-row gap-4 lg:gap-6 px-4 pb-5 pt-16 sm:px-8 sm:pb-7">
            <div className="flex-1 min-w-0 flex flex-col gap-2.5 sm:gap-3">
              <h1 className="text-white text-3xl sm:text-5xl font-medium uppercase leading-tight break-words"
                style={{ textShadow: '0 6px 26px rgba(0,0,0,.8)' }}>
                {house.name}
              </h1>
              {house.description && (
                <p className="max-w-2xl text-white/80 text-sm sm:text-[15px] font-light leading-relaxed whitespace-pre-wrap break-words"
                  style={{ textShadow: '0 2px 10px rgba(0,0,0,.8)' }}>
                  {house.description}
                </p>
              )}
              <div className="flex items-center gap-x-5 gap-y-2 mt-1 flex-wrap text-xs sm:text-[12.5px] text-white/75">
                <span className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-stat-energy shadow-[0_0_8px_#88B332] animate-pulse" />
                  <b className="text-white font-medium">{inside.length}</b> сейчас в доме
                </span>
                <Link to={`/location/${house.location_id}`} className="site-link flex items-center gap-1">
                  <MapPin size={13} />{house.location_name ?? `Локация #${house.location_id}`}
                </Link>
                {house.owner && (
                  <span className="flex items-center gap-2 min-w-0">
                    Хозяин:
                    <CharAvatar src={house.owner.avatar} size="w-6 h-6" />
                    <span className="text-white truncate">{house.owner.name}</span>
                  </span>
                )}
              </div>
              {characterBar}
              {character && (
                <div className="flex flex-col gap-2 pt-2 sm:max-w-md">
                  <button type="button" onClick={onEnter} disabled={entering || !atHouseLocation}
                    className="btn-blue !w-full sm:!w-auto !px-8 self-start flex items-center justify-center gap-2 disabled:opacity-50">
                    <DoorOpen size={16} />{entering ? 'Входим...' : 'Войти в дом'}
                  </button>
                  <span className="text-white/50 text-xs leading-snug">
                    {atHouseLocation
                      ? 'Войти можно мгновенно. Внутри комнаты как обычные локации — переходите между ними в панели «Комнаты дома».'
                      : 'Дойдите до локации, где стоит дом, чтобы войти.'}
                  </span>
                </div>
              )}
            </div>
            {panel}
          </div>
        </section>

        <section className={PANEL}>
          <div className={PANEL_HEAD}>
            <Users size={17} className="text-gold shrink-0" />
            <h2 className="gold-text text-[13px] font-medium uppercase tracking-[0.08em]">Кто в доме</h2>
            <span className="ml-auto bg-white/10 text-white/60 text-[10px] font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">{inside.length}</span>
          </div>
          <PresentList people={inside} note="Сейчас в доме никого нет." />
        </section>
      </div>
    );
  }

  // --- A room ---
  const Icon = ROOM_TYPE_ICON[room.room_type];
  const built = room.level >= 1;
  const present = room.present ?? [];
  const inRoom = acting?.room_id === room.id;
  const letIn = acting != null && acting.room_ids.includes(room.id);
  const moveHere = character && letIn && built && !inRoom ? () => onMove(room) : null;
  const ownerActing = house.acting.find((a) => a.is_owner && a.character) ?? null;
  const isStorage = STORAGE_ROOMS.includes(room.room_type);
  const actorProps = { room, acting, houseLocationId: house.location_id, frozen, onChanged };

  if (!room.can_read) {
    return (
      <div className="flex flex-col gap-4 sm:gap-5">
        <div className="flex flex-col lg:flex-row gap-4 lg:gap-6">
          <div className="flex-1 min-w-0 bg-site-bg backdrop-blur-sm rounded-card border border-white/10 p-6 text-white/80 flex items-center gap-3 self-start">
            <Lock size={18} className="text-gold shrink-0" />Комната закрыта — читать её могут только впущенные в неё.
          </div>
          {panel}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 sm:gap-5">
      <section className="relative h-auto lg:max-h-[400px] rounded-card overflow-hidden bg-site-bg backdrop-blur-sm border border-gold-dark/20 shadow-card flex flex-col">
        <div className="absolute top-4 left-4 right-4 sm:top-5 sm:left-6 flex items-center gap-2 flex-wrap">
          <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-[11px] font-medium uppercase tracking-[0.06em] shadow-card bg-green-600/80 text-green-100 border-green-300/40">
            <ShieldCheck size={13} />Безопасная
          </span>
          <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-site-bg border border-gold-dark/60 text-gold text-[11px] font-medium uppercase tracking-[0.06em]">
            <Icon size={12} />{ROOM_TYPE_LABEL[room.room_type]}
          </span>
          {built && (
            <span className="px-3 py-1.5 rounded-full bg-site-bg border border-gold-dark/60 text-gold-light text-[11px] font-medium tracking-[0.06em]">
              Ур. {room.level}
            </span>
          )}
          {!room.is_open && (
            <span className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-black/50 text-gold text-[11px]"><Lock size={12} />Закрыта</span>
          )}
        </div>

        <div className="relative flex-1 min-h-0 flex flex-col lg:flex-row gap-4 lg:gap-6 px-4 pb-5 pt-[4.5rem] sm:pt-16 sm:px-8 sm:pb-7">
          <div className="flex-1 min-w-0 flex flex-col gap-2.5 sm:gap-3 lg:overflow-y-auto gold-scrollbar">
            <h1 className="text-white text-3xl sm:text-5xl font-medium uppercase leading-tight break-words"
              style={{ textShadow: '0 6px 26px rgba(0,0,0,.8)' }}>
              {room.name}
            </h1>
            {room.description && (
              <p className="max-w-2xl text-white/80 text-sm sm:text-[15px] font-light leading-relaxed whitespace-pre-wrap break-words"
                style={{ textShadow: '0 2px 10px rgba(0,0,0,.8)' }}>
                {room.description}
              </p>
            )}
            <div className="flex items-center gap-x-5 gap-y-2 mt-1 flex-wrap text-xs sm:text-[12.5px] text-white/75">
              <span className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-stat-energy shadow-[0_0_8px_#88B332] animate-pulse" />
                <b className="text-white font-medium">{present.length}</b> сейчас здесь
              </span>
              <span className="flex items-center gap-2">
                <MessageSquare size={14} className="text-site-blue shrink-0" />
                <b className="text-white font-medium">{room.posts_count}</b> постов
              </span>
              <span className="flex items-center gap-2 min-w-0">
                <Home size={14} className="text-gold shrink-0" />
                <span className="truncate">Дом <b className="text-white font-medium">{house.name}</b></span>
              </span>
            </div>
            <BuildStatus room={room} onDone={onChanged} className="text-sm" />
            <div className="flex flex-wrap gap-1.5" aria-label="Что можно делать в комнате">
              {functionChips(room).map((c) => (
                <span key={c.text} className={CHIP}>
                  <c.icon size={12} className="text-gold shrink-0" /><span className="break-words">{c.text}</span>
                </span>
              ))}
            </div>
            {characterBar}
          </div>
          {panel}
        </div>
      </section>

      {character && !inRoom && (
        <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 rounded-card border border-gold-dark/40 bg-gold/10 backdrop-blur-sm px-4 py-3">
          <span className="flex-1 min-w-0 text-white/85 text-sm">
            «{character.name}» {standingRoom ? <>сейчас в комнате «{standingRoom.name}»</> : 'сейчас не в доме'} — здесь можно только смотреть.
            {!letIn && ' Хозяин не пускал этого персонажа в эту комнату.'}
          </span>
          {moveHere && (
            <button type="button" onClick={moveHere} disabled={movingRoomId != null}
              className="btn-blue !w-full sm:!w-auto !px-6 !py-1.5 !text-sm shrink-0 flex items-center justify-center gap-1.5 disabled:opacity-50">
              <Footprints size={14} />{movingRoomId === room.id ? 'Переходим...' : 'Перейти сюда'}
            </button>
          )}
        </div>
      )}

      {/* «Что здесь есть» and «Кто здесь» — one row, equal height, matching headers */}
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_330px] gap-4 sm:gap-5 lg:items-stretch">
          <section className={`${PANEL} flex flex-col min-w-0 order-2 lg:order-1`}>
            <div className={PANEL_HEAD}>
              <Icon size={17} className="text-gold shrink-0" />
              <h2 className="gold-text text-[13px] font-medium uppercase tracking-[0.08em]">Что здесь есть</h2>
              <InfoTooltip content={roomInfoContent(room)} label={`Что даёт комната «${ROOM_TYPE_LABEL[room.room_type]}»`} />
            </div>
            <div className="p-4 sm:p-5 flex flex-col gap-4">
              <div className={`${ACTION_BAR} empty:hidden`}>
                <SleepControl room={room} acting={acting} houseLocationId={house.location_id} onChanged={onChanged} frozen={frozen} />
                <BathControl {...actorProps} />
                <LibraryControl {...actorProps} />
                <ShrineControl {...actorProps} />
                {isStorage && built && acting && <StorageControl houseId={house.id} acting={acting} />}
              </div>
              <GardenBeds {...actorProps} />
              <ReturnCircleInfo room={room} />
              <TrophyHall houseId={house.id} houseLocationId={house.location_id} room={room} owner={ownerActing}
                houseBonus={house.trophy_bonus ?? 0} frozen={frozen} onChanged={onChanged} />

              {room.room_type !== 'trophy_hall' && room.furniture_group != null && (
                <div className="flex flex-col gap-2">
                  <div className="flex items-center gap-2">
                    <Armchair size={13} className="text-gold shrink-0" />
                    <span className="text-white/60 text-[11px] uppercase tracking-[0.06em]">Обстановка</span>
                    <span className="text-white/40 text-[11px]">{(room.furniture ?? []).length}/{room.furniture_slots ?? room.level}</span>
                    <InfoTooltip size={12} label="Об обстановке"
                      content="Мебель даёт комнате бонусы. Её расставляет хозяин во вкладке «Управление домом»; мест столько, каков уровень комнаты." />
                  </div>
                  {(room.furniture ?? []).length === 0 ? (
                    <p className="text-white/40 text-xs">Мебели пока нет.</p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {room.furniture.map((piece) => (
                        <WithTooltip key={piece.id} tapToggle className="block"
                          content={
                            <span className="flex flex-col gap-0.5">
                              <span className="text-white">{piece.name}</span>
                              <span className="text-gold-light">{furnitureBonusText(room.furniture_group, piece)}</span>
                              {piece.description && <span>{piece.description}</span>}
                            </span>
                          }>
                          <span className="flex items-center justify-center w-14 h-14 rounded-card border border-white/[0.1] bg-white/[0.03] hover:border-gold/50 transition-colors duration-200 ease-site">
                            <FurnitureIcon name={piece.name} image={piece.image} rarity={piece.rarity} title="" />
                          </span>
                        </WithTooltip>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>

        <section className={`${PANEL} flex flex-col order-1 lg:order-2`}>
          <div className={PANEL_HEAD}>
            <Users size={17} className="text-gold shrink-0" />
            <h2 className="gold-text text-[13px] font-medium uppercase tracking-[0.08em]">Кто здесь</h2>
            <span className="ml-auto bg-white/10 text-white/60 text-[10px] font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">{present.length}</span>
          </div>
          <PresentList people={present} note="В комнате сейчас никого нет." />
        </section>
      </div>

      {/* Posts span the full page width, like on a location */}
      <RoomPosts room={room} acting={acting} frozen={frozen} onMoveHere={moveHere} />
    </div>
  );
};

export default HouseRoomView;
