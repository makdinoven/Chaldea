import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import type { TreeNodeInTreeResponse, NodeVisualState } from './types';

interface PlayerNodeData extends TreeNodeInTreeResponse {
  visualState: NodeVisualState;
}

const stateStyles: Record<
  NodeVisualState,
  { border: string; bg: string; extra: string; opacity: string }
> = {
  chosen: {
    border: 'border-green-400',
    bg: 'bg-green-900/60',
    extra: 'shadow-[0_0_18px_rgba(74,222,128,0.6)]',
    opacity: 'opacity-100',
  },
  available: {
    border: 'border-gold',
    bg: 'bg-yellow-900/50',
    extra: 'shadow-[0_0_16px_rgba(240,217,92,0.5)] animate-pulse',
    opacity: 'opacity-100',
  },
  locked: {
    border: 'border-white/30',
    bg: 'bg-black/50',
    extra: '',
    opacity: 'opacity-70',
  },
  blocked: {
    border: 'border-site-red/50',
    bg: 'bg-red-900/30',
    extra: '',
    opacity: 'opacity-60',
  },
};

const PlayerNodeComponent = ({ data, selected }: NodeProps) => {
  const nodeData = data as PlayerNodeData;
  const skillsCount = nodeData.skills?.length ?? 0;
  const state = nodeData.visualState ?? 'locked';
  const style = stateStyles[state];

  const isClickable = state === 'available' || state === 'chosen';

  return (
    <div
      className={`
        relative flex flex-col items-center justify-center
        w-[100px] h-[100px] rounded-full
        border-2 ${style.border} ${style.bg} ${style.extra} ${style.opacity}
        backdrop-blur-sm transition-all duration-200 ease-site
        ${isClickable ? 'cursor-pointer' : 'cursor-default'}
        ${selected ? 'ring-2 ring-site-blue ring-offset-2 ring-offset-transparent' : ''}
      `}
      title={
        state === 'locked'
          ? `Требуется уровень ${nodeData.level_ring}`
          : state === 'blocked'
            ? 'Альтернативная ветка выбрана'
            : undefined
      }
    >
      {/* Handles for edges */}
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2 !h-2 !bg-white/20 !border-0 !-top-1"
      />

      {/* Level ring badge */}
      <span className="absolute -top-2 -right-2 bg-site-bg text-white text-[10px] font-medium rounded-full w-6 h-6 flex items-center justify-center border border-white/20">
        {nodeData.level_ring}
      </span>

      {/* Blocked X icon */}
      {state === 'blocked' && (
        <span className="absolute top-1 left-1 text-site-red text-xs font-bold">
          &#10005;
        </span>
      )}

      {/* Node name */}
      <span className="text-white text-[11px] font-medium text-center leading-tight px-2 line-clamp-2">
        {nodeData.name}
      </span>

      {/* Skills count badge */}
      {skillsCount > 0 && (
        <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 bg-site-blue text-white text-[9px] font-medium rounded-full px-1.5 py-0.5 min-w-[18px] text-center">
          {skillsCount}
        </span>
      )}

      {/* Chosen checkmark */}
      {state === 'chosen' && (
        <span className="absolute -bottom-2.5 right-0 text-green-400 text-sm">
          &#10003;
        </span>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2 !h-2 !bg-white/20 !border-0 !-bottom-1"
      />
    </div>
  );
};

export default memo(PlayerNodeComponent);
