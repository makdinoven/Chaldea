/** FEAT-198/199 staff labels shared by «Нераскрытые дела» and the character card «Закон» panel. */

export const CRIME_TYPE_LABELS: Record<string, string> = {
  npc_kill: 'Убийство НПС',
  guard_defeat: 'Нападение на стражу',
  jail_escape: 'Побег из тюрьмы',
  caravan_attack: 'Нападение на караван',
  pvp_attack: 'Нападение на персонажа',
  theft: 'Кража',
  /** FEAT-207: never carries the faction (crime rows have no faction data). */
  faction_membership: 'Членство в запрещённой фракции',
};

export const CRIME_STATUS_LABELS: Record<string, string> = {
  reported: 'Замечено',
  unwitnessed: 'Не замечено',
  masked: 'В маске',
  closed: 'Закрыто',
  pending_witness: 'Ждёт свидетеля',
};

/** Text colour of a crime status chip. */
export const CRIME_STATUS_CLASSES: Record<string, string> = {
  reported: 'text-site-red',
  unwitnessed: 'text-gold',
  masked: 'text-gold',
  closed: 'text-white/50',
};

/** Deferred crimes that can still be revealed or closed (`law_core.CRIME_OPEN`). */
export const OPEN_CRIME_STATUSES: readonly string[] = ['unwitnessed', 'masked'];

export const isOpenCrime = (status: string): boolean => OPEN_CRIME_STATUSES.includes(status);

/** «Замечено» or «Раскрыто» (a deferred crime that was revealed later). */
export const crimeStatusLabel = (status: string, revealedAt: string | null | undefined): string =>
  status === 'reported' && revealedAt ? 'Раскрыто' : CRIME_STATUS_LABELS[status] ?? status;

export const RENOWN_SOURCE_LABELS: Record<string, string> = {
  quest: 'Задание',
  reputation: 'Репутация',
  crime: 'Преступление',
  staff: 'Решение властей',
};

export const RENOWN_SCALE_LABELS: Record<string, string> = {
  fame: 'Слава',
  infamy: 'Дурная слава',
};

export const SUSPICION_CLASSES: Record<string, string> = {
  uneasy: 'text-gold',
  alarmed: 'text-orange-300',
  fear: 'text-site-red',
};

/** Percent without trailing zeros: 12.5 → «12.5 %». */
export const pct = (v: number | null | undefined): string => (v == null ? '—' : `${Number(v.toFixed(2))} %`);
