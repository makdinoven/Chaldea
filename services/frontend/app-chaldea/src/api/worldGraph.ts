import axios from 'axios';
import { BASE_URL } from './api';

export type MarkerType = 'safe' | 'dangerous' | 'dungeon' | 'farm';

export interface GraphArea {
  id: number;
  name: string;
  sort_order: number;
}

export interface GraphCountry {
  id: number;
  name: string;
  area_id: number | null;
}

export interface GraphRegion {
  id: number;
  name: string;
  country_id: number;
}

export interface GraphDistrict {
  id: number;
  name: string;
  region_id: number;
}

export interface GraphLocation {
  id: number;
  name: string;
  region_id: number;
  country_id: number;
  district_id: number | null;
  marker_type: MarkerType;
  recommended_level: number;
  no_quick_move: boolean;
  quick_travel_marker: boolean;
}

/**
 * One entry per unordered pair. `cost_ba` is null when only the a -> b row
 * exists in the DB, which makes the edge genuinely one-way for routing.
 */
export interface GraphEdge {
  a: number;
  b: number;
  cost_ab: number | null;
  cost_ba: number | null;
  auto: boolean;
}

export interface GraphStats {
  locations: number;
  edges: number;
  isolated: number;
  one_way_edges: number;
  duplicate_rows: number;
}

export interface WorldGraph {
  areas: GraphArea[];
  countries: GraphCountry[];
  regions: GraphRegion[];
  districts: GraphDistrict[];
  locations: GraphLocation[];
  edges: GraphEdge[];
  stats: GraphStats;
}

/** Public endpoint — no auth token required. */
export const fetchWorldGraph = async (): Promise<WorldGraph> => {
  const { data } = await axios.get<WorldGraph>(`${BASE_URL}/locations/map/graph`);
  return data;
};
