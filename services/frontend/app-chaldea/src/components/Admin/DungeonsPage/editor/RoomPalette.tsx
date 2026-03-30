import { ROOM_TYPE_ICONS, ROOM_TYPE_LABELS, ROOM_COLORS } from './constants';
import type { RoomType } from './types';

const ROOM_TYPES: RoomType[] = [
  'battle', 'boss', 'treasure', 'trap', 'event',
  'rest', 'merchant', 'fork', 'teleport', 'deadend',
];

const onDragStart = (event: React.DragEvent, roomType: string) => {
  event.dataTransfer.setData('application/reactflow', roomType);
  event.dataTransfer.effectAllowed = 'move';
};

const RoomPalette = () => {
  return (
    <div className="gray-bg flex flex-col gap-1.5 p-3 rounded-lg h-full overflow-y-auto">
      <h3 className="gold-text text-sm font-medium uppercase tracking-[0.06em] mb-1 px-1">
        Комнаты
      </h3>

      {ROOM_TYPES.map((type) => {
        const icon = ROOM_TYPE_ICONS[type] ?? '❓';
        const label = ROOM_TYPE_LABELS[type] ?? type;
        const color = ROOM_COLORS[type] ?? '#374151';

        return (
          <div
            key={type}
            draggable
            onDragStart={(e) => onDragStart(e, type)}
            className="flex items-center gap-2.5 px-3 py-2 rounded-md cursor-grab active:cursor-grabbing
                       bg-white/[0.04] hover:bg-white/[0.1] transition-colors duration-150 select-none"
            title={label}
          >
            <span
              className="w-7 h-7 flex items-center justify-center rounded text-base shrink-0"
              style={{ backgroundColor: color }}
            >
              {icon}
            </span>
            <span className="text-sm text-white/80 truncate">{label}</span>
          </div>
        );
      })}
    </div>
  );
};

export default RoomPalette;
