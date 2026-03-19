export interface AvatarFrame {
  id: string;
  label: string;
  borderStyle: string;
  shadow: string;
}

export const AVATAR_FRAMES: readonly AvatarFrame[] = [
  { id: 'gold', label: 'Золотая', borderStyle: '3px solid #f0d95c', shadow: '0 0 12px rgba(240, 217, 92, 0.4)' },
  { id: 'silver', label: 'Серебряная', borderStyle: '3px solid #c0c0c0', shadow: '0 0 12px rgba(192, 192, 192, 0.4)' },
  { id: 'fire', label: 'Огненная', borderStyle: '3px solid #ff6347', shadow: '0 0 15px rgba(255, 99, 71, 0.5)' },
] as const;
