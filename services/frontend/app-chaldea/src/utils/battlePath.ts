import { getClientPrefs } from './clientPrefs';
import { isWebGLAvailable } from '../components/pages/BattlePage/Arena3D/webgl';

/**
 * The address of a battle in the view this browser prefers: the 3D table
 * when the player chose it in the settings and the device can draw it,
 * otherwise the 2D board.
 */
export const battlePath = (locationId: number | string, battleId: number | string): string => {
  const wants3D = getClientPrefs().battleView === '3d' && isWebGLAvailable();
  return `/location/${locationId}/${wants3D ? 'battle3d' : 'battle'}/${battleId}`;
};
