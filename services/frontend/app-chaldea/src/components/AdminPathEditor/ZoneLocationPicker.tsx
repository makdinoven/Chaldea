import { useEffect, useRef, useState } from 'react';

interface LocationOption {
  id: number;
  name: string;
}

interface ZoneLocationPickerProps {
  locations: LocationOption[];
  position: { x: number; y: number };
  containerRef: React.RefObject<HTMLDivElement | null>;
  onSelect: (locationId: number) => void;
  onClose: () => void;
}

const ZoneLocationPicker = ({ locations, position, containerRef, onSelect, onClose }: ZoneLocationPickerProps) => {
  const ref = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<React.CSSProperties>({ visibility: 'hidden' });

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  // Position the dropdown using fixed coordinates, flipping up if needed
  useEffect(() => {
    const container = containerRef.current;
    const dropdown = ref.current;
    if (!container || !dropdown) return;

    const rect = container.getBoundingClientRect();
    const anchorX = rect.left + (position.x / 100) * rect.width;
    const anchorY = rect.top + (position.y / 100) * rect.height;

    const dropdownRect = dropdown.getBoundingClientRect();
    const dropdownHeight = dropdownRect.height;
    const dropdownWidth = dropdownRect.width;

    const spaceBelow = window.innerHeight - anchorY - 8;
    const openUpward = spaceBelow < dropdownHeight && anchorY > dropdownHeight;

    let left = anchorX - dropdownWidth / 2;
    // Keep within viewport horizontally
    if (left < 4) left = 4;
    if (left + dropdownWidth > window.innerWidth - 4) left = window.innerWidth - 4 - dropdownWidth;

    setStyle({
      position: 'fixed',
      left: `${left}px`,
      top: openUpward ? `${anchorY - dropdownHeight - 8}px` : `${anchorY + 8}px`,
      visibility: 'visible',
    });
  }, [position, containerRef]);

  if (locations.length === 0) return null;

  return (
    <div
      ref={ref}
      className="z-50 dropdown-menu min-w-[160px] max-h-[300px] overflow-y-auto py-1"
      style={style}
    >
      <p className="px-3 py-1 text-xs text-white/50 uppercase tracking-wide">
        Выберите локацию
      </p>
      {locations.map((loc) => (
        <button
          key={loc.id}
          className="dropdown-item w-full text-left text-sm"
          onClick={() => {
            onSelect(loc.id);
            onClose();
          }}
        >
          {loc.name}
        </button>
      ))}
    </div>
  );
};

export default ZoneLocationPicker;
