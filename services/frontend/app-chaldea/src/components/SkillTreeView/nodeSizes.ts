/**
 * Rendered size of a skill tree node, in pixels.
 *
 * The layout, the canvas and the admin editor all need this to place a node on
 * its centre, so it lives in one place rather than being repeated as a literal
 * in each of them.
 */

/*
  Sized against the wheel rather than against nothing. The binding constraint is
  where two sectors nearly meet at ring 5: their nearest nodes are 24° apart, so
  at that ring's radius their centres are only ~110px apart. These sizes keep
  ~30px of daylight there while filling the 200px-plus emptiness between
  neighbours on a ring. Raising them further means pushing ring 5 outward too —
  see innerRadius in combineTrees.
*/

/** Ordinary nodes. */
export const NODE_SIZE_REGULAR = 80;

/**
 * Subclass picks — the one landmark worth enlarging.
 *
 * Class roots deliberately stay ordinary size: they sit at the very centre,
 * inside the painted hub, and an enlarged root spilled out of it.
 */
export const NODE_SIZE_LARGE = 120;

export const playerNodeSize = (nodeType: string | undefined | null): number =>
  nodeType === 'subclass_choice' ? NODE_SIZE_LARGE : NODE_SIZE_REGULAR;
