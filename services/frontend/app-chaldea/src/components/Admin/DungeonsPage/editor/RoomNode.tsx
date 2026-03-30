import { Handle, Position, type NodeProps } from 'reactflow';
import type { RoomNodeData } from './types';
import { ROOM_COLORS, ROOM_TYPE_ICONS } from './constants';

const handleStyle = {
  width: 8,
  height: 8,
  opacity: 0,
  transition: 'opacity 0.15s',
  background: '#d4d4d8',
  border: '1px solid #71717a',
};

const truncate = (text: string, max: number) =>
  text.length > max ? text.slice(0, max) + '...' : text;

const RoomNode = ({ data, selected }: NodeProps<RoomNodeData>) => {
  const { room } = data;
  const bgColor = ROOM_COLORS[room.room_type] ?? '#374151';
  const icon = ROOM_TYPE_ICONS[room.room_type] ?? '❓';

  const isEntrance = room.is_entrance;
  const isBoss = room.is_boss_room;
  const isManaCore = room.is_mana_core_room;

  // Build border / shadow classes
  let borderStyle = '';
  let shadowStyle = '';

  if (isEntrance) {
    borderStyle = '2px dashed gold';
  } else if (selected) {
    borderStyle = '2px solid #60a5fa';
  } else {
    borderStyle = '1px solid rgba(255,255,255,0.15)';
  }

  if (isBoss) {
    shadowStyle = '0 0 14px 4px rgba(239,68,68,0.6)';
  } else if (isManaCore) {
    shadowStyle = '0 0 14px 4px rgba(168,85,247,0.6)';
  } else if (selected) {
    shadowStyle = '0 0 8px 2px rgba(96,165,250,0.5)';
  }

  return (
    <div
      className="group relative flex flex-col items-center justify-center rounded-lg cursor-pointer select-none"
      style={{
        width: 120,
        height: 120,
        backgroundColor: bgColor,
        border: borderStyle,
        boxShadow: shadowStyle || undefined,
      }}
      onClick={() => data.onSelect(room)}
    >
      {/* Room type icon */}
      <span className="text-3xl leading-none mb-1 drop-shadow">{icon}</span>

      {/* Room name */}
      <span className="text-[11px] leading-tight text-white/90 font-medium text-center px-1 max-w-[110px] truncate">
        {truncate(room.name, 12)}
      </span>

      {/* Dirty / new indicator */}
      {(data.isDirty || data.isNew) && (
        <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-yellow-400" />
      )}

      {/* Source handles — 3 per side */}
      <Handle type="source" position={Position.Top} id="t-1" style={{ ...handleStyle, top: -4, left: '25%' }} className="group-hover:!opacity-80" />
      <Handle type="source" position={Position.Top} id="t-2" style={{ ...handleStyle, top: -4, left: '50%' }} className="group-hover:!opacity-80" />
      <Handle type="source" position={Position.Top} id="t-3" style={{ ...handleStyle, top: -4, left: '75%' }} className="group-hover:!opacity-80" />
      <Handle type="source" position={Position.Bottom} id="b-1" style={{ ...handleStyle, bottom: -4, left: '25%' }} className="group-hover:!opacity-80" />
      <Handle type="source" position={Position.Bottom} id="b-2" style={{ ...handleStyle, bottom: -4, left: '50%' }} className="group-hover:!opacity-80" />
      <Handle type="source" position={Position.Bottom} id="b-3" style={{ ...handleStyle, bottom: -4, left: '75%' }} className="group-hover:!opacity-80" />
      <Handle type="source" position={Position.Left} id="l-1" style={{ ...handleStyle, left: -4, top: '25%' }} className="group-hover:!opacity-80" />
      <Handle type="source" position={Position.Left} id="l-2" style={{ ...handleStyle, left: -4, top: '50%' }} className="group-hover:!opacity-80" />
      <Handle type="source" position={Position.Left} id="l-3" style={{ ...handleStyle, left: -4, top: '75%' }} className="group-hover:!opacity-80" />
      <Handle type="source" position={Position.Right} id="r-1" style={{ ...handleStyle, right: -4, top: '25%' }} className="group-hover:!opacity-80" />
      <Handle type="source" position={Position.Right} id="r-2" style={{ ...handleStyle, right: -4, top: '50%' }} className="group-hover:!opacity-80" />
      <Handle type="source" position={Position.Right} id="r-3" style={{ ...handleStyle, right: -4, top: '75%' }} className="group-hover:!opacity-80" />

      {/* Target handles — same positions, same IDs (React Flow distinguishes by type) */}
      <Handle type="target" position={Position.Top} id="t-1" style={{ ...handleStyle, top: -4, left: '25%' }} className="group-hover:!opacity-80" />
      <Handle type="target" position={Position.Top} id="t-2" style={{ ...handleStyle, top: -4, left: '50%' }} className="group-hover:!opacity-80" />
      <Handle type="target" position={Position.Top} id="t-3" style={{ ...handleStyle, top: -4, left: '75%' }} className="group-hover:!opacity-80" />
      <Handle type="target" position={Position.Bottom} id="b-1" style={{ ...handleStyle, bottom: -4, left: '25%' }} className="group-hover:!opacity-80" />
      <Handle type="target" position={Position.Bottom} id="b-2" style={{ ...handleStyle, bottom: -4, left: '50%' }} className="group-hover:!opacity-80" />
      <Handle type="target" position={Position.Bottom} id="b-3" style={{ ...handleStyle, bottom: -4, left: '75%' }} className="group-hover:!opacity-80" />
      <Handle type="target" position={Position.Left} id="l-1" style={{ ...handleStyle, left: -4, top: '25%' }} className="group-hover:!opacity-80" />
      <Handle type="target" position={Position.Left} id="l-2" style={{ ...handleStyle, left: -4, top: '50%' }} className="group-hover:!opacity-80" />
      <Handle type="target" position={Position.Left} id="l-3" style={{ ...handleStyle, left: -4, top: '75%' }} className="group-hover:!opacity-80" />
      <Handle type="target" position={Position.Right} id="r-1" style={{ ...handleStyle, right: -4, top: '25%' }} className="group-hover:!opacity-80" />
      <Handle type="target" position={Position.Right} id="r-2" style={{ ...handleStyle, right: -4, top: '50%' }} className="group-hover:!opacity-80" />
      <Handle type="target" position={Position.Right} id="r-3" style={{ ...handleStyle, right: -4, top: '75%' }} className="group-hover:!opacity-80" />
    </div>
  );
};

export default RoomNode;
