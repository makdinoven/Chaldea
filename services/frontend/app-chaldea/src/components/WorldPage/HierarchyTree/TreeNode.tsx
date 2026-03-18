import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import type { HierarchyNode } from '../../../redux/actions/worldMapActions';

interface TreeNodeProps {
  node: HierarchyNode;
  depth: number;
  currentLocationId: number | null;
  onNavigate?: () => void;
}

const TYPE_LABELS: Record<string, string> = {
  area: 'Область',
  country: 'Страна',
  region: 'Регион',
  district: 'Зона',
  location: 'Локация',
};

const MARKER_ICONS: Record<string, string> = {
  safe: '🏠',
  dangerous: '⚔️',
  dungeon: '🏰',
};

const getNodeRoute = (node: HierarchyNode): string | null => {
  switch (node.type) {
    case 'area':
      return `/world/area/${node.id}`;
    case 'country':
      return `/world/country/${node.id}`;
    case 'region':
      return `/world/region/${node.id}`;
    case 'location':
      return `/location/${node.id}`;
    default:
      return null;
  }
};

const hasLocationDescendant = (node: HierarchyNode, locationId: number): boolean => {
  if (node.type === 'location' && node.id === locationId) return true;
  return node.children.some((child) => hasLocationDescendant(child, locationId));
};

const TreeNode = ({ node, depth, currentLocationId, onNavigate }: TreeNodeProps) => {
  const navigate = useNavigate();
  const hasChildren = node.children.length > 0;
  const isCurrentLocation = node.type === 'location' && node.id === currentLocationId;
  const containsCurrentLocation = currentLocationId !== null && hasLocationDescendant(node, currentLocationId);

  const [isExpanded, setIsExpanded] = useState(containsCurrentLocation);

  const handleClick = () => {
    const route = getNodeRoute(node);
    if (route) {
      navigate(route);
      onNavigate?.();
    }
  };

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsExpanded(!isExpanded);
  };

  const paddingLeft = depth * 16 + 8;

  return (
    <div>
      <div
        className={`
          flex items-center gap-1 py-1.5 px-2 rounded-lg cursor-pointer
          transition-colors duration-200 ease-site
          ${isCurrentLocation ? 'bg-white/[0.12]' : 'hover:bg-white/[0.07]'}
        `}
        style={{ paddingLeft: `${paddingLeft}px` }}
        onClick={handleClick}
      >
        {/* Expand/collapse toggle */}
        {hasChildren ? (
          <button
            onClick={handleToggle}
            className="w-5 h-5 flex items-center justify-center text-white/60 hover:text-white
                       transition-colors duration-200 ease-site shrink-0"
          >
            <motion.span
              animate={{ rotate: isExpanded ? 90 : 0 }}
              transition={{ duration: 0.15 }}
              className="block text-xs"
            >
              ▶
            </motion.span>
          </button>
        ) : (
          <span className="w-5 h-5 shrink-0" />
        )}

        {/* Marker icon for locations */}
        {node.type === 'location' && node.marker_type && (
          <span className="text-xs shrink-0" title={TYPE_LABELS[node.type]}>
            {MARKER_ICONS[node.marker_type] ?? ''}
          </span>
        )}

        {/* Node label */}
        <span
          className={`
            text-sm truncate
            ${isCurrentLocation ? 'text-gold font-medium' : 'text-white hover:text-site-blue'}
            transition-colors duration-200 ease-site
          `}
          title={`${TYPE_LABELS[node.type] ?? node.type}: ${node.name}`}
        >
          {node.name}
        </span>

        {/* Type badge for higher levels */}
        {(node.type === 'area' || node.type === 'country') && (
          <span className="text-[10px] text-white/40 uppercase tracking-wider ml-auto shrink-0">
            {TYPE_LABELS[node.type]}
          </span>
        )}
      </div>

      {/* Children */}
      <AnimatePresence initial={false}>
        {isExpanded && hasChildren && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="overflow-hidden"
          >
            {node.children.map((child) => (
              <TreeNode
                key={`${child.type}-${child.id}`}
                node={child}
                depth={depth + 1}
                currentLocationId={currentLocationId}
                onNavigate={onNavigate}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default TreeNode;
