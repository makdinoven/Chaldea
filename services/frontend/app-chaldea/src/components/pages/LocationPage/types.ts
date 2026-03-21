export interface Player {
  id: number;
  name: string;
  avatar: string | null;
  level: number;
  class_name: string | null;
  race_name: string | null;
}

export interface NeighborLocation {
  id: number;
  name: string;
  energy_cost: number;
  image_url: string | null;
  recommended_level: number;
}

export interface Post {
  post_id: number;
  character_id: number;
  character_photo: string | null;
  character_title: string | null;
  character_name: string;
  user_id: number;
  user_nickname: string;
  content: string;
  length: number;
  created_at: string;
  likes_count: number;
  liked_by: number[];
}

export interface LocationData {
  id: number;
  name: string;
  description: string;
  type: string;
  recommended_level: number;
  image_url: string | null;
  marker_type: string;
  neighbors: NeighborLocation[];
  players: Player[];
  posts: Post[];
}

export type MarkerType = 'safe' | 'dangerous' | 'dungeon' | 'farm';
