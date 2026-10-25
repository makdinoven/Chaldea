import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import toast from 'react-hot-toast';
import DungeonVisualEditor from './DungeonVisualEditor';
import DungeonGeneratorModal from './DungeonGeneratorModal';
import DungeonStatusControl from './DungeonStatusControl';
import type { Dungeon, DungeonRoom, DungeonCorridor } from '../../../api/dungeons';
import { updateDungeon, validateDungeon } from '../../../api/dungeons';

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
  const [generatorOpen, setGeneratorOpen] = useState(false);

  const dungeonId = Number(id);

  const [switching, setSwitching] = useState(false);

  /** Show the dungeon on its location or hide it. A dungeon that fails the check is not switched on. */
  const toggleActive = async () => {
    if (!dungeon) return;
    setSwitching(true);
    try {
      if (!dungeon.is_active) {
        const check = await validateDungeon(dungeonId);
        if (!check.valid) {
          toast.error(`Сначала исправьте: ${check.errors[0]}`);
          return;
        }
      }
      await updateDungeon(dungeonId, { is_active: !dungeon.is_active });
      toast.success(dungeon.is_active ? 'Подземелье скрыто с локации' : 'Подземелье включено и видно на локации');
      await loadDungeon(true);
    } catch {
      toast.error('Не удалось переключить подземелье');
    } finally {
      setSwitching(false);
    }
  };

  /** `quiet`: refresh under the open page (the generator's window stays up). */
  const loadDungeon = async (quiet = false) => {
    if (!quiet) setLoading(true);
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
      void loadDungeon();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dungeonId]);

  if (loading) {
    return (
      <div className="w-full max-w-container mx-auto flex flex-col gap-6">
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  if (error || !dungeon) {
    return (
      <div className="w-full max-w-container mx-auto flex flex-col gap-6">
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
        <button
          type="button"
          onClick={() => void toggleActive()}
          disabled={switching}
          title={dungeon.is_active ? 'Скрыть подземелье с локации' : 'Показать подземелье на локации'}
          className={`px-3 py-1 rounded-full text-xs font-medium self-start transition-colors disabled:opacity-50 ${
            dungeon.is_active
              ? 'bg-green-500/20 text-green-300 hover:bg-green-500/30'
              : 'bg-site-red/30 text-site-red hover:bg-site-red/40'
          }`}
        >
          {switching ? '...' : dungeon.is_active ? 'Активно — выключить' : 'Неактивно — включить'}
        </button>
      </div>

      {dungeon.description && (
        <p className="text-white/70 text-sm">{dungeon.description}</p>
      )}

      <div className="flex flex-wrap items-center gap-4 text-sm text-white/70">
        <span>Комнат: <span className="text-white">{rooms.length}</span></span>
        <span>Коридоров: <span className="text-white">{corridors.length}</span></span>
        <span>Рек. уровень: <span className="text-white">{dungeon.recommended_level ?? '—'}</span></span>
        <span>Рек. группа: <span className="text-white">{dungeon.recommended_party_size ?? '—'}</span></span>
        <button onClick={() => setGeneratorOpen(true)} className="btn-blue !text-sm !px-4 !py-1.5">
          Сгенерировать
        </button>
      </div>

      <DungeonGeneratorModal
        open={generatorOpen}
        onClose={() => setGeneratorOpen(false)}
        dungeonId={dungeonId}
        roomsCount={rooms.length}
        defaultLevel={dungeon.recommended_level}
        defaultPartySize={dungeon.recommended_party_size}
        defaultTheme={dungeon.theme}
        onGenerated={() => void loadDungeon(true)}
      />

      <DungeonStatusControl dungeonId={dungeonId} />

      {/* Visual Editor */}
      <DungeonVisualEditor
        dungeonId={dungeonId}
        dungeonName={dungeon.name}
        theme={dungeon.theme}
        floorThemes={dungeon.floor_themes}
        rooms={rooms}
        corridors={corridors}
        onUpdate={() => void loadDungeon()}
      />
    </div>
  );
};

export default AdminDungeonDetail;
