import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import toast from 'react-hot-toast';
import type { DungeonRoom } from '../../../api/dungeons';

interface AdminDungeonRoomsProps {
  dungeonId: number;
  rooms: DungeonRoom[];
  onUpdate: () => void;
}

const ROOM_TYPE_LABELS: Record<string, string> = {
  battle: 'Бой',
  boss: 'Босс',
  treasure: 'Сокровищница',
  trap: 'Ловушка',
  event: 'Событие',
  rest: 'Отдых',
  merchant: 'Торговец',
  fork: 'Развилка',
  teleport: 'Телепорт',
  deadend: 'Тупик',
};

const ROOM_TYPE_COLORS: Record<string, string> = {
  battle: 'bg-site-red/30 text-site-red',
  boss: 'bg-red-900/40 text-red-300',
  treasure: 'bg-gold/20 text-gold',
  trap: 'bg-orange-500/30 text-orange-300',
  event: 'bg-purple-500/30 text-purple-300',
  rest: 'bg-green-500/30 text-green-300',
  merchant: 'bg-site-blue/30 text-site-blue',
  fork: 'bg-white/10 text-white/70',
  teleport: 'bg-cyan-500/30 text-cyan-300',
  deadend: 'bg-amber-800/30 text-amber-400',
};

const AdminDungeonRooms = ({ dungeonId, rooms, onUpdate }: AdminDungeonRoomsProps) => {
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState<number | null>(null);

  const handleDelete = async (roomId: number) => {
    if (!window.confirm('Удалить комнату? Все связанные коридоры тоже будут удалены.')) return;
    setDeleting(roomId);
    try {
      await axios.delete(`/dungeons/admin/rooms/${roomId}`);
      toast.success('Комната удалена');
      onUpdate();
    } catch {
      toast.error('Не удалось удалить комнату');
    } finally {
      setDeleting(null);
    }
  };

  const sorted = [...rooms].sort((a, b) => a.sort_order - b.sort_order);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <h2 className="text-white text-lg font-medium uppercase tracking-[0.06em]">
          Комнаты ({rooms.length})
        </h2>
        <button
          className="btn-blue !text-base !px-6 !py-2"
          onClick={() => navigate(`/admin/dungeons/${dungeonId}/rooms/create`)}
        >
          Добавить комнату
        </button>
      </div>

      {rooms.length === 0 ? (
        <p className="text-center text-white/50 text-sm py-8">
          Комнаты ещё не добавлены
        </p>
      ) : (
        <div className="gray-bg overflow-hidden">
          {/* Desktop table */}
          <div className="hidden md:block">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Название</th>
                  <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Тип</th>
                  <th className="text-center text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Вход</th>
                  <th className="text-center text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Босс</th>
                  <th className="text-center text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Порядок</th>
                  <th className="text-right text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Действия</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((room) => (
                  <tr key={room.id} className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200">
                    <td className="px-4 py-3 text-sm text-white">{room.name}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${ROOM_TYPE_COLORS[room.room_type] || ''}`}>
                        {ROOM_TYPE_LABELS[room.room_type] || room.room_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center text-sm">
                      {room.is_entrance ? <span className="text-gold">Да</span> : <span className="text-white/30">—</span>}
                    </td>
                    <td className="px-4 py-3 text-center text-sm">
                      {room.is_boss_room ? <span className="text-site-red">Да</span> : <span className="text-white/30">—</span>}
                    </td>
                    <td className="px-4 py-3 text-center text-sm text-white/70">{room.sort_order}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col items-end gap-1.5">
                        <button
                          onClick={() => navigate(`/admin/dungeons/${dungeonId}/rooms/${room.id}/edit`)}
                          className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                        >
                          Редактировать
                        </button>
                        <button
                          onClick={() => handleDelete(room.id)}
                          disabled={deleting === room.id}
                          className="text-sm text-site-red hover:text-white transition-colors duration-200 disabled:opacity-30"
                        >
                          {deleting === room.id ? 'Удаление...' : 'Удалить'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="md:hidden flex flex-col gap-3 p-3">
            {sorted.map((room) => (
              <div key={room.id} className="bg-white/[0.03] rounded-card p-4 flex flex-col gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex flex-col gap-1 min-w-0">
                    <span className="text-white text-sm font-medium truncate">
                      {room.name}
                    </span>
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${ROOM_TYPE_COLORS[room.room_type] || ''}`}>
                        {ROOM_TYPE_LABELS[room.room_type] || room.room_type}
                      </span>
                      {room.is_entrance && <span className="text-gold text-[10px]">Вход</span>}
                      {room.is_boss_room && <span className="text-site-red text-[10px]">Босс</span>}
                    </div>
                  </div>
                  <span className="text-white/50 text-xs ml-auto shrink-0">#{room.sort_order}</span>
                </div>
                <div className="flex gap-3 flex-wrap">
                  <button
                    onClick={() => navigate(`/admin/dungeons/${dungeonId}/rooms/${room.id}/edit`)}
                    className="text-sm text-white hover:text-site-blue transition-colors"
                  >
                    Редактировать
                  </button>
                  <button
                    onClick={() => handleDelete(room.id)}
                    disabled={deleting === room.id}
                    className="text-sm text-site-red hover:text-white transition-colors disabled:opacity-30"
                  >
                    {deleting === room.id ? 'Удаление...' : 'Удалить'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminDungeonRooms;
