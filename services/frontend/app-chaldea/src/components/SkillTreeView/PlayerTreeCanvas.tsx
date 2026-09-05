import { useMemo, useCallback, useEffect, useRef, useState } from 'react';
import ReactFlow, {
  Controls,
  type Node,
  type Edge,
  type NodeMouseHandler,
  type ReactFlowInstance,
} from 'reactflow';
import 'reactflow/dist/style.css';
import PlayerNodeComponent from './PlayerNodeComponent';
import { computeNodeState } from './utils/computeNodeState';
import { combineTrees } from './utils/combineTrees';
import { GradientEdge, BridgeEdge, classGradientColors, defaultGradient } from './treeEdges';
import { playerNodeSize } from './nodeSizes';
import type {
  FullClassTreeResponse,
  CharacterTreeProgressResponse,
  NodeVisualState,
} from './types';

import warriorArt from '../../assets/skillTreeWarrior.png';
import mageArt from '../../assets/skillTreeMage.png';
import rogueArt from '../../assets/skillTreeRogue.png';
import WheelBackdrop from './WheelBackdrop';

/* Map class_id -> art image (DB: 1=Warrior, 2=Rogue, 3=Mage) */
const classArtMap: Record<number, string> = {
  1: warriorArt,
  2: rogueArt,
  3: mageArt,
};

export interface TreeView {
  tree: FullClassTreeResponse;
  progress: CharacterTreeProgressResponse | null;
  /** Another class's tree: visible for reference, but nothing in it is choosable. */
  readOnly: boolean;
}

interface PlayerTreeCanvasProps {
  views: TreeView[];
  onNodeClick: (nodeId: number) => void;
}

/** Gap between the outermost node and the edge of the round frame, in pixels. */
const WHEEL_EDGE_PADDING = 50;

/**
 * How far the painted backdrop is knocked back. Light: the nodes carry their
 * own opaque core and glow, so the art does not need to be dimmed to keep them
 * readable, and dimming it only made the wheel look murky.
 */
const WHEEL_BACKDROP_DIM = 0.12;

/** Admin nodes are 100px boxes positioned by their top-left corner. */
const ADMIN_NODE_SIZE = 100;

const PlayerTreeCanvas = ({ views, onNodeClick }: PlayerTreeCanvasProps) => {
  const nodeTypes = useMemo(() => ({
    playerNode: PlayerNodeComponent,
  }), []);

  const edgeTypes = useMemo(() => ({
    gradient: GradientEdge,
    bridge: BridgeEdge,
  }), []);

  const combined = views.length > 1;

  const { nodes, edges, wheelRadius } = useMemo(() => {
    // In combined mode the trees are arranged into one wheel; in single-tree
    // mode the authored coordinates are used as-is.
    const layout = combined ? combineTrees(views.map((v) => v.tree)) : null;

    const rfNodes: Node[] = [];
    const rfEdges: Edge[] = [];

    for (const view of views) {
      const { tree, progress, readOnly } = view;
      const chosenNodeIds = new Set(
        (progress?.chosen_nodes ?? []).map((cn) => cn.node_id),
      );
      const characterLevel = progress?.character_level ?? 0;

      for (const apiNode of tree.nodes) {
        // A foreign tree carries no progress, so every node in it would come
        // out "locked" anyway — but say so explicitly rather than relying on
        // that, so a foreign root never pulses as if it were available.
        const visualState: NodeVisualState = readOnly
          ? 'locked'
          : computeNodeState(
              apiNode,
              tree.connections,
              chosenNodeIds,
              characterLevel,
              tree.nodes,
            );

        // The wheel hands back node centres; the single-tree view uses the
        // authored top-left coordinates, whose centre is half an admin node in.
        const placed = layout?.positions.get(String(apiNode.id));
        const centreX = placed?.x ?? apiNode.position_x + ADMIN_NODE_SIZE / 2;
        const centreY = placed?.y ?? apiNode.position_y + ADMIN_NODE_SIZE / 2;
        const half = playerNodeSize(apiNode.node_type ?? 'regular') / 2;

        rfNodes.push({
          id: String(apiNode.id),
          type: 'playerNode',
          position: { x: centreX - half, y: centreY - half },
          data: {
            ...apiNode,
            visualState,
            classId: tree.class_id,
            foreign: readOnly,
          },
          draggable: false,
          selectable: true,
          connectable: false,
        });
      }

      /* ---------- Edges with gradient styling ---------- */
      const gradient = classGradientColors[tree.class_id] ?? defaultGradient;
      const ringOf = new Map(tree.nodes.map((n) => [String(n.id), n.level_ring ?? 1]));
      for (const conn of tree.connections) {
        const sourceChosen = chosenNodeIds.has(Number(conn.from_node_id));
        const targetChosen = chosenNodeIds.has(Number(conn.to_node_id));
        const bothChosen = sourceChosen && targetChosen;
        const oneChosen = sourceChosen || targetChosen;

        // A link has to show the player where a branch leads, over a painted
        // backdrop, so even an untouched one is drawn in full class colour.
        // The tiers separate by weight, not by fading towards invisible.
        let colors: [string, string] = gradient.strong;
        let strokeWidth = 2;
        let glowing = false;
        let opacity = 1;

        if (bothChosen) {
          colors = gradient.bright;
          strokeWidth = 3;
          glowing = true;
        } else if (oneChosen) {
          strokeWidth = 2.5;
        } else if (readOnly) {
          // Another class's branches are always the faintest thing on screen:
          // fainter than anything in the player's own sector, reachable or not.
          colors = gradient.faint;
          strokeWidth = 1.5;
          opacity = 0.45;
        } else {
          // Rings the character cannot reach yet recede, so the branches that
          // are actually in play stand out from the rest of their own sector.
          const reach = Math.max(
            ringOf.get(String(conn.from_node_id)) ?? 0,
            ringOf.get(String(conn.to_node_id)) ?? 0,
          );
          if (reach > characterLevel) {
            strokeWidth = 1.75;
            opacity = 0.7;
          }
        }

        rfEdges.push({
          id: String(conn.id ?? `edge-${conn.from_node_id}-${conn.to_node_id}`),
          source: String(conn.from_node_id),
          target: String(conn.to_node_id),
          type: 'gradient',
          data: { colors, strokeWidth, glowing, opacity, curved: combined, casing: combined },
        });
      }
    }

    for (const bridge of layout?.bridges ?? []) {
      rfEdges.push({
        id: bridge.id,
        source: bridge.fromNodeId,
        target: bridge.toNodeId,
        type: 'bridge',
        focusable: false,
        interactionWidth: 0,
      });
    }

    // Radius of the whole wheel, measured to the outer edge of the furthest
    // node. Used to centre and scale the pinned view.
    let wheelRadius = 0;
    if (combined) {
      for (const node of rfNodes) {
        const half = playerNodeSize((node.data as { node_type?: string }).node_type ?? 'regular') / 2;
        const centre = Math.hypot(node.position.x + half, node.position.y + half);
        wheelRadius = Math.max(wheelRadius, centre + half);
      }
    }

    return { nodes: rfNodes, edges: rfEdges, wheelRadius };
  }, [views, combined]);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      onNodeClick(Number(node.id));
    },
    [onNodeClick]
  );

  // The class art only makes sense behind a single class's tree; the combined
  // wheel spans all three, so it gets the plain vignette instead.
  const classArt = combined ? null : classArtMap[views[0]?.tree.class_id ?? 1] ?? warriorArt;

  // Lock minZoom to fitView level + compute translate bounds from node positions
  const [initialZoom, setInitialZoom] = useState<number | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [instance, setInstance] = useState<ReactFlowInstance | null>(null);

  /*
    fitView centres the *bounding box*, and a three-fold wheel with one sector
    pointing up does not have a box centred on its hub: it reaches r upward but
    only r·sin(54°) downward. Centring that box pushes the top class towards the
    edge and leaves the other two with room to spare. So the pinned wheel sets
    its own viewport: hub at the centre of the frame, scaled to leave exactly
    WHEEL_EDGE_PADDING outside the last ring.
  */
  useEffect(() => {
    const el = wrapperRef.current;
    if (!combined || !instance || !el || wheelRadius <= 0) return;

    const apply = () => {
      const { width, height } = el.getBoundingClientRect();
      if (!width || !height) return;
      const usable = Math.min(width, height) / 2 - WHEEL_EDGE_PADDING;
      if (usable <= 0) return;
      instance.setViewport({ x: width / 2, y: height / 2, zoom: usable / wheelRadius });
    };

    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(el);
    return () => observer.disconnect();
  }, [combined, instance, wheelRadius]);

  const translateExtent = useMemo((): [[number, number], [number, number]] => {
    if (nodes.length === 0) return [[-Infinity, -Infinity], [Infinity, Infinity]];
    const xs = nodes.map((n) => n.position.x);
    const ys = nodes.map((n) => n.position.y);
    const pad = 150; // extra padding around edges
    return [
      [Math.min(...xs) - pad, Math.min(...ys) - pad],
      [Math.max(...xs) + pad, Math.max(...ys) + pad],
    ];
  }, [nodes]);

  return (
    <div ref={wrapperRef} className="relative w-full h-full min-h-[400px] overflow-hidden">
      {combined ? (
        /*
          The backdrop is one circle split into the same three sectors in the
          same order — red warrior up, green rogue lower right, blue mage lower
          left — so it registers with the layout rather than sitting behind it.
        */
        <WheelBackdrop dim={WHEEL_BACKDROP_DIM} />
      ) : (
        <>
          {/* ---- Class art as fixed background ---- */}
          {classArt && (
            <div
              className="absolute inset-0 pointer-events-none"
              style={{
                backgroundImage: `url(${classArt})`,
                backgroundSize: 'cover',
                backgroundPosition: 'center',
                opacity: 0.25,
              }}
            />
          )}

          {/* ---- Dark radial vignette over the art ---- */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background:
                'radial-gradient(circle at 50% 50%, rgba(10,10,18,0.15) 0%, rgba(10,10,18,0.6) 55%, rgba(10,10,18,0.9) 80%)',
            }}
          />

          {/* ---- Subtle grid overlay ---- */}
          <div
            className="absolute inset-0 pointer-events-none opacity-[0.04]"
            style={{
              backgroundImage:
                'linear-gradient(rgba(255,255,255,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.15) 1px, transparent 1px)',
              backgroundSize: '40px 40px',
            }}
          />
        </>
      )}

      {/* ---- ReactFlow canvas ---- */}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={true}
        // The wheel is meant to be taken in whole, so it is pinned: no panning,
        // no zooming, and the page keeps scrolling over it. The single-class
        // view still needs both, since it fills the screen on a phone.
        panOnDrag={!combined}
        panOnScroll={false}
        zoomOnScroll={!combined}
        zoomOnPinch={!combined}
        zoomOnDoubleClick={!combined}
        preventScrolling={!combined}
        fitView={!combined}
        fitViewOptions={{ padding: 0.1 }}
        minZoom={initialZoom ?? 0.1}
        maxZoom={2.5}
        translateExtent={translateExtent}
        onInit={(flow) => {
          setInstance(flow);
          if (combined) return; // the wheel drives its own viewport
          // After fitView, lock minZoom to current zoom (= fully zoomed out state)
          setTimeout(() => {
            const { zoom } = flow.getViewport();
            setInitialZoom(zoom);
          }, 150);
        }}
        defaultEdgeOptions={{ type: 'default' }}
        className="!bg-transparent"
        style={{ position: 'relative', zIndex: 2 }}
        proOptions={{ hideAttribution: true }}
      >
        {!combined && (
        <Controls
          showInteractive={false}
          className="
            !bg-[#1a1a2e]/80 !border-white/5 !rounded-lg !shadow-none
            [&_button]:!bg-transparent [&_button]:!border-white/5
            [&_button]:!fill-white/50 [&_button:hover]:!fill-white
            [&_button:hover]:!bg-white/5
          "
        />
        )}
      </ReactFlow>
    </div>
  );
};

export default PlayerTreeCanvas;
