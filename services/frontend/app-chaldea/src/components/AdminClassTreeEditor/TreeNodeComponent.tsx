import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import type { TreeNodeInTreeResponse } from './types';

/**
 * Color-coded ring border based on level_ring.
 */
const getRingColor = (levelRing: number, nodeType: string): string => {
  if (nodeType === 'subclass_choice') return 'border-yellow-500 shadow-[0_0_12px_rgba(240,217,92,0.5)]';
  if (nodeType === 'root') return 'border-green-400 shadow-[0_0_8px_rgba(74,222,128,0.4)]';
  if (levelRing <= 1) return 'border-green-400';
  if (levelRing <= 10) return 'border-sky-400';
  if (levelRing <= 20) return 'border-purple-400';
  if (levelRing <= 25) return 'border-orange-400';
  if (levelRing <= 30) return 'border-yellow-500';
  return 'border-teal-400';
};

const getRingBg = (levelRing: number, nodeType: string): string => {
  if (nodeType === 'subclass_choice') return 'bg-yellow-500/20';
  if (nodeType === 'root') return 'bg-green-400/15';
  if (levelRing <= 1) return 'bg-green-400/10';
  if (levelRing <= 10) return 'bg-sky-400/10';
  if (levelRing <= 20) return 'bg-purple-400/10';
  if (levelRing <= 25) return 'bg-orange-400/10';
  if (levelRing <= 30) return 'bg-yellow-500/10';
  return 'bg-teal-400/10';
};

const TreeNodeComponent = ({ data, selected }: NodeProps) => {
  const nodeData = data as TreeNodeInTreeResponse;
  const skillsCount = nodeData.skills?.length ?? 0;
  const ringColor = getRingColor(nodeData.level_ring, nodeData.node_type);
  const ringBg = getRingBg(nodeData.level_ring, nodeData.node_type);

  return (
    <div
      className={`
        relative flex flex-col items-center justify-center
        w-[100px] h-[100px] rounded-full
        border-2 ${ringColor} ${ringBg}
        backdrop-blur-sm cursor-pointer
        transition-all duration-200 ease-site
        ${selected ? 'ring-2 ring-site-blue ring-offset-2 ring-offset-transparent' : ''}
      `}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-3 !h-3 !bg-gold !border-gold-dark !-top-1.5"
      />

      {/* Level ring badge */}
      <span className="absolute -top-2 -right-2 bg-site-bg text-white text-[10px] font-medium rounded-full w-6 h-6 flex items-center justify-center border border-white/20">
        {nodeData.level_ring}
      </span>

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

      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-3 !h-3 !bg-gold !border-gold-dark !-bottom-1.5"
      />
    </div>
  );
};

export default memo(TreeNodeComponent);
