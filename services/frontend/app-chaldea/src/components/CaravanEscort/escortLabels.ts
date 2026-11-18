/** FEAT-212 — Russian labels of the escort panel. */

export const ESCORT_STATE_LABEL: Record<string, string> = {
  preparing: 'Караван собирается в путь',
  on_road: 'Караван в пути',
  held: 'Караван стоит',
  under_attack: 'На караван напали!',
  arrived: 'Караван прибыл — ждёт расчёта',
};

export const ESCORT_STATE_CLS: Record<string, string> = {
  preparing: 'text-gold',
  on_road: 'text-site-blue',
  held: 'text-white/70',
  under_attack: 'text-site-red',
  arrived: 'text-stat-energy',
};

export const ESCORT_RAID_LABEL: Record<string, string> = {
  starting: 'налётчики нападают',
  fighting: 'идёт бой с налётчиками',
  won: 'караван ограблен',
  repelled: 'налёт отбит — надбавка при доставке',
  aborted: 'бой прерван',
  expired: 'налёт сорвался',
};

/** Raid statuses while the fight is on (leaving is refused). */
export const ACTIVE_RAID: ReadonlySet<string> = new Set(['starting', 'fighting']);

export const stateLabel = (state: string): string => ESCORT_STATE_LABEL[state] ?? state;

/** FEAT-215: the sea stage of the escorted caravan in plain words; null on land / unknown stage. */
export const seaStageLabel = (
  stage: string | null | undefined,
  board: string | null | undefined,
  alight: string | null | undefined,
  ship: string | null | undefined,
): string | null => {
  switch (stage) {
    case 'to_port':
      return `Едет в порт ${board ?? ''}`.trim() + ' — там погрузится на корабль';
    case 'waiting':
      return `Ждёт корабль в порту ${board ?? ''}`.trim();
    case 'aboard':
      return `В трюме корабля${ship ? ` «${ship}»` : ''}${alight ? ` — плывёт в ${alight}` : ''}`;
    case 'landed':
      return `Сошёл в порту ${alight ?? ''}`.trim() + ' — дальше по суше';
    case 'stranded':
      return 'Корабль потерян — караван возвращается';
    default:
      return null;
  }
};
