/**
 * Rendered size of a skill tree node, in pixels.
 *
 * The layout, the canvas and the admin editor all need this to place a node on
 * its centre, so it lives in one place rather than being repeated as a literal
 * in each of them.
 */

/*
  Sized against the wheel rather than against nothing: on the current trees the
  tightest spot is where two sectors nearly meet at ring 5, where node centres
  are ~100px apart. These sizes leave ~36px of clear space there, while cutting
  the emptiness between neighbours on a ring, which runs to 200px and more.
*/

/** Ordinary nodes. */
export const NODE_SIZE_REGULAR = 64;

/** Class roots and subclass picks — the landmarks of a tree. */
export const NODE_SIZE_LARGE = 96;

export const playerNodeSize = (nodeType: string | undefined | null): number =>
  nodeType === 'root' || nodeType === 'subclass_choice' ? NODE_SIZE_LARGE : NODE_SIZE_REGULAR;
