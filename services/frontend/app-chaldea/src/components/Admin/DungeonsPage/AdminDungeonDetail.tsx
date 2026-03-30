import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import toast from 'react-hot-toast';
import DungeonVisualEditor from './DungeonVisualEditor';
import type { Dungeon, DungeonRoom, DungeonCorridor } from '../../../api/dungeons';

const STABILITY_LABELS: Record<string, string> = {
  static: 'Статичный',
  unstable: 'Нестабильный',
  chaotic: 'Хаотичный',
};

const AdminDungeonDetail = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [dungeon, setDungeon] = useState<Dungeon | null>(null);
  const [rooms, setRooms] = useState<DungeonRoom[]>([]);
  const [corridors, setCorridors] = useState<DungeonCorridor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const dungeonId = Number(id);

  const loadDungeon = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await axios.get(`/dungeons/admin/dungeons/${dungeonId}`);
      setDungeon(data);
      setRooms(data.rooms || []);
      setCorridors(data.corridors || []);
    } catch {
      setError('Не удалось загрузить данные подземелья');
      toast.error('Ошибка загрузки подземелья');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (dungeonId) {
      loadDungeon();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dungeonId]);

  if (loading) {
    return (
      <div className="w-full max-w-[1240px] mx-auto flex flex-col gap-6">
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  if (error || !dungeon) {
    return (
      <div className="w-full max-w-[1240px] mx-auto flex flex-col gap-6">
        <div className="text-site-red text-sm">{error || 'Подземелье не найдено'}</div>
        <button onClick={() => navigate('/admin/dungeons')} className="btn-line !w-auto !px-6">
          Назад к списку
        </button>
      </div>
    );
  }

  return (
    <div className="w-full flex flex-col gap-4 px-2">
      {/* Back button */}
      <button
        onClick={() => navigate('/admin/dungeons')}
        className="text-sm text-white/50 hover:text-site-blue transition-colors duration-200 self-start"
      >
        &larr; Назад к списку подземелий
      </button>

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">
          {dungeon.name}
        </h1>
        <span className="px-3 py-1 rounded-full text-xs font-medium self-start bg-white/20 text-white">
          {STABILITY_LABELS[dungeon.stability_type] || dungeon.stability_type}
        </span>
        {!dungeon.is_active && (
          <span className="px-3 py-1 rounded-full text-xs font-medium self-start bg-site-red/30 text-site-red">
            Неактивно
          </span>
        )}
      </div>

      {dungeon.description && (
        <p className="text-white/70 text-sm">{dungeon.description}</p>
      )}

      <div className="flex flex-wrap items-center gap-4 text-sm text-white/70">
        <span>Комнат: <span className="text-white">{rooms.length}</span></span>
        <span>Коридоров: <span className="text-white">{corridors.length}</span></span>
        <span>Рек. уровень: <span className="text-white">{dungeon.recommended_level ?? '—'}</span></span>
        <span>Рек. группа: <span className="text-white">{dungeon.recommended_party_size ?? '—'}</span></span>
        <button
          onClick={async () => {
            try {
              await axios.delete(`/dungeons/admin/dungeons/${dungeonId}/cooldown`);
              toast.success('Кулдаун снят');
            } catch {
              toast.error('Не удалось снять кулдаун');
            }
          }}
          className="text-xs text-site-red hover:text-white transition-colors"
        >
          Снять кулдаун
        </button>
      </div>

      {/* Visual Editor */}
      <DungeonVisualEditor
        dungeonId={dungeonId}
        rooms={rooms}
        corridors={corridors}
        onUpdate={loadDungeon}
      />
    </div>
  );
};

export default AdminDungeonDetail;
