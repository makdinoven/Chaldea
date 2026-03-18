import { useCallback, useEffect, useRef, useState } from 'react';

interface BackgroundPositionPickerProps {
  imageUrl: string;
  position: string;
  onChange: (position: string) => void;
}

const parsePosition = (pos: string): { x: number; y: number } => {
  const parts = pos.trim().split(/\s+/);
  const x = parseFloat(parts[0]) || 50;
  const y = parseFloat(parts[1]) || 50;
  return { x: Math.max(0, Math.min(100, x)), y: Math.max(0, Math.min(100, y)) };
};

const BackgroundPositionPicker = ({ imageUrl, position, onChange }: BackgroundPositionPickerProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const startPos = useRef({ clientX: 0, clientY: 0 });
  const startBgPos = useRef({ x: 50, y: 50 });
  const [currentPos, setCurrentPos] = useState(() => parsePosition(position));
  const imageSize = useRef({ width: 0, height: 0 });

  useEffect(() => {
    setCurrentPos(parsePosition(position));
  }, [position]);

  // Preload the image to know its natural dimensions
  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      imageSize.current = { width: img.naturalWidth, height: img.naturalHeight };
    };
    img.src = imageUrl;
  }, [imageUrl]);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      dragging.current = true;
      startPos.current = { clientX: e.clientX, clientY: e.clientY };
      startBgPos.current = { ...currentPos };
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    },
    [currentPos],
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!dragging.current || !containerRef.current) return;

      const rect = containerRef.current.getBoundingClientRect();
      const deltaX = e.clientX - startPos.current.clientX;
      const deltaY = e.clientY - startPos.current.clientY;

      // Convert pixel delta to percentage of the container.
      // Moving the mouse right should decrease background-position-x
      // (to reveal the right side of the image), hence the negative sign.
      const pctX = (deltaX / rect.width) * 100;
      const pctY = (deltaY / rect.height) * 100;

      const newX = Math.max(0, Math.min(100, startBgPos.current.x - pctX));
      const newY = Math.max(0, Math.min(100, startBgPos.current.y - pctY));

      setCurrentPos({ x: newX, y: newY });
    },
    [],
  );

  const handlePointerUp = useCallback(() => {
    if (!dragging.current) return;
    dragging.current = false;
    setCurrentPos((pos) => {
      const x = Math.round(pos.x);
      const y = Math.round(pos.y);
      onChange(`${x}% ${y}%`);
      return { x, y };
    });
  }, [onChange]);

  const positionStr = `${Math.round(currentPos.x)}% ${Math.round(currentPos.y)}%`;

  return (
    <div className="flex flex-col gap-2">
      <div
        ref={containerRef}
        className="w-full rounded-card overflow-hidden select-none touch-none"
        style={{
          aspectRatio: '16 / 5',
          backgroundImage: `url(${imageUrl})`,
          backgroundSize: 'cover',
          backgroundPosition: positionStr,
          backgroundRepeat: 'no-repeat',
          cursor: dragging.current ? 'grabbing' : 'grab',
        }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      />
      <p className="text-white/30 text-xs text-center">
        Перетащите для позиционирования
      </p>
    </div>
  );
};

export default BackgroundPositionPicker;
