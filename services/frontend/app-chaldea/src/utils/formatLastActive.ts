const ONLINE_THRESHOLD_MINUTES = 5;

/**
 * Format last_active_at into a Russian human-readable string.
 * Returns online status or relative time.
 */
export const formatLastActive = (dateStr: string | null): string => {
  if (!dateStr) {
    return 'Никогда не заходил(а)';
  }

  const lastActive = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - lastActive.getTime();
  const diffMinutes = Math.floor(diffMs / 60000);

  if (diffMinutes < ONLINE_THRESHOLD_MINUTES) {
    return 'Онлайн';
  }

  if (diffMinutes < 60) {
    return `Был(а) ${diffMinutes} ${pluralMinutes(diffMinutes)} назад`;
  }

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `Был(а) ${diffHours} ${pluralHours(diffHours)} назад`;
  }

  const diffDays = Math.floor(diffHours / 24);
  return `Был(а) ${diffDays} ${pluralDays(diffDays)} назад`;
};

/**
 * Check if a user is online (last active within 5 minutes).
 */
export const isOnline = (dateStr: string | null): boolean => {
  if (!dateStr) return false;
  const lastActive = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - lastActive.getTime();
  return diffMs < ONLINE_THRESHOLD_MINUTES * 60000;
};

// Russian plural forms for time units

const pluralMinutes = (n: number): string => {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'минуту';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return 'минуты';
  return 'минут';
};

const pluralHours = (n: number): string => {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'час';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return 'часа';
  return 'часов';
};

const pluralDays = (n: number): string => {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'день';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return 'дня';
  return 'дней';
};
