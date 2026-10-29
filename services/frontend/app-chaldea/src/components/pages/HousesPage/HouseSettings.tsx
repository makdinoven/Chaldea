import { useState } from 'react';
import toast from 'react-hot-toast';
import {
  updateHouse,
  updateRoom,
  ROOM_TYPE_LABEL,
  roomProfessionName,
  type House,
  type HouseRoom,
} from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import { FIELD, LABEL } from '../EpisodesPage/EpisodeFormModal';
import ImageField from '../EpisodesPage/ImageField';

interface HouseSettingsProps {
  house: House;
  ownerCharacterId: number;
  onChanged: () => void;
}

interface RoomFormProps {
  houseId: number;
  room: HouseRoom;
  ownerCharacterId: number;
  onChanged: () => void;
}

/** One room's name, description, picture and whether everyone may read it. */
const RoomForm = ({ houseId, room, ownerCharacterId, onChanged }: RoomFormProps) => {
  const [name, setName] = useState(room.name);
  const [description, setDescription] = useState(room.description);
  const [image, setImage] = useState<string | null>(room.image_url);
  const [isOpen, setIsOpen] = useState(room.is_open);
  const profession = roomProfessionName(room.room_type);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!name.trim()) {
      toast.error('Введите название комнаты');
      return;
    }
    setSaving(true);
    try {
      await updateRoom(houseId, room.id, {
        character_id: ownerCharacterId,
        name: name.trim(),
        description,
        image_url: image,
        is_open: isOpen,
      });
      toast.success(`«${name.trim()}» сохранена`);
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить комнату'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <article className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] p-4 flex flex-col gap-3">
      <span className="text-gold text-xs uppercase tracking-[0.06em]">
        {ROOM_TYPE_LABEL[room.room_type]}
        {profession && <span className="text-white/45 normal-case tracking-normal"> · профессия: {profession}</span>}
      </span>
      <label className="flex flex-col gap-1.5">
        <span className={LABEL}>Название</span>
        <input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} className={FIELD} />
      </label>
      <label className="flex flex-col gap-1.5">
        <span className={LABEL}>Описание</span>
        <textarea value={description} maxLength={5000} onChange={(e) => setDescription(e.target.value)}
          className={`${FIELD} resize-y min-h-[90px]`} />
      </label>
      <ImageField label="Картинка" value={image} onChange={setImage} />
      <label className="flex items-start gap-3 cursor-pointer">
        <input type="checkbox" checked={isOpen} onChange={(e) => setIsOpen(e.target.checked)} className="mt-1 accent-gold" />
        <span className="flex flex-col">
          <span className="text-white text-sm">Открыта для всех</span>
          <span className="text-white/45 text-xs">Читать комнату смогут все, кого вы пускаете в дом. Писать — только вы и жильцы с доступом.</span>
        </span>
      </label>
      <button type="button" onClick={() => void save()} disabled={saving}
        className="btn-blue !w-full sm:!w-auto !px-6 self-end disabled:opacity-50">
        {saving ? 'Сохранение...' : 'Сохранить комнату'}
      </button>
    </article>
  );
};

/** The owner's settings: the house itself and every room. */
const HouseSettings = ({ house, ownerCharacterId, onChanged }: HouseSettingsProps) => {
  const [name, setName] = useState(house.name);
  const [description, setDescription] = useState(house.description);
  const [image, setImage] = useState<string | null>(house.image_url);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!name.trim()) {
      toast.error('Введите название дома');
      return;
    }
    setSaving(true);
    try {
      await updateHouse(house.id, { character_id: ownerCharacterId, name: name.trim(), description, image_url: image });
      toast.success('Дом сохранён');
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить дом'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <section className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 p-4 sm:p-5 flex flex-col gap-3">
        <h2 className="gold-text text-sm font-medium uppercase tracking-[0.08em]">Дом</h2>
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Название</span>
          <input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} className={FIELD} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Описание</span>
          <textarea value={description} maxLength={5000} onChange={(e) => setDescription(e.target.value)}
            className={`${FIELD} resize-y min-h-[110px]`} />
        </label>
        <ImageField label="Картинка" value={image} onChange={setImage} />
        <button type="button" onClick={() => void save()} disabled={saving}
          className="btn-blue !w-full sm:!w-auto !px-6 self-end disabled:opacity-50">
          {saving ? 'Сохранение...' : 'Сохранить дом'}
        </button>
      </section>

      <div className="flex flex-col gap-3">
        <h2 className="gold-text text-sm font-medium uppercase tracking-[0.08em]">Комнаты</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {house.rooms.map((room) => (
            <RoomForm key={room.id} houseId={house.id} room={room} ownerCharacterId={ownerCharacterId}
              onChanged={onChanged} />
          ))}
          {house.rooms.length === 0 && (
            <p className="text-white/40 text-sm italic">Комнат пока нет — постройте их во вкладке «Стройка».</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default HouseSettings;
