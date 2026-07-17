import axios from "axios";

/* ── Party-service client (FEAT-144). `party.ts` is the battle lobby, so this
      module is named squads. ── */

const makeClient = (baseURL: string) => {
  const client = axios.create({ baseURL, withCredentials: true, timeout: 10000 });
  client.interceptors.request.use((config) => {
    const token = localStorage.getItem("accessToken");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });
  client.interceptors.response.use(
    (r) => r,
    (e) => {
      if (e.response) {
        const detail = e.response.data?.detail;
        throw new Error(
          typeof detail === "string" ? detail : e.response.statusText || "Ошибка запроса",
        );
      }
      throw new Error("Сеть недоступна");
    },
  );
  return client;
};

const partyClient = makeClient("/party");
const charClient = makeClient("/characters");

/* ── Types ── */

export interface PartyMember {
  character_id: number;
  user_id: number;
  name: string | null;
  avatar: string | null;
  is_leader: boolean;
  status: "invited" | "accepted";
  current_location_id: number | null;
  /* FEAT-151 — enriched member payload (all nullable; hide UI when null) */
  level?: number | null;
  class_name?: string | null;
  current_health?: number | null;
  max_health?: number | null;
  current_mana?: number | null;
  max_mana?: number | null;
}

export interface Party {
  id: number;
  name: string;
  avatar: string | null;
  leader_character_id: number;
  members: PartyMember[];
}

export interface IncomingInvite {
  party_id: number;
  party_name: string;
  party_avatar: string | null;
  leader_character_id: number;
  leader_name: string | null;
}

export interface PlayerOnLocation {
  id: number;
  name: string;
  avatar: string | null;
  level?: number;
}

export interface PartyOnLocationMember {
  character_id: number;
  name: string | null;
  avatar: string | null;
  is_leader: boolean;
}

export interface PartyOnLocation {
  id: number;
  name: string;
  avatar: string | null;
  leader_character_id: number;
  members: PartyOnLocationMember[];
}

/* ── Calls ── */

export const getMyParty = async (characterId: number): Promise<Party | null> => {
  const { data } = await partyClient.get("/mine", { params: { character_id: characterId } });
  return data ?? null;
};

export const getIncomingInvites = async (characterId: number): Promise<IncomingInvite[]> => {
  const { data } = await partyClient.get("/invites/incoming", {
    params: { character_id: characterId },
  });
  return data ?? [];
};

export const createParty = async (
  leaderCharacterId: number,
  name: string,
  avatar?: string | null,
): Promise<Party> => {
  const { data } = await partyClient.post("/", {
    leader_character_id: leaderCharacterId,
    name,
    avatar: avatar ?? null,
  });
  return data;
};

export const invitePlayer = async (partyId: number, characterId: number): Promise<Party> => {
  const { data } = await partyClient.post(`/${partyId}/invite`, { character_id: characterId });
  return data;
};

export const respondInvite = async (
  partyId: number,
  characterId: number,
  accept: boolean,
): Promise<Party | null> => {
  const { data } = await partyClient.post(`/${partyId}/respond`, {
    character_id: characterId,
    accept,
  });
  return data ?? null;
};

export const leaveParty = async (partyId: number, characterId: number): Promise<void> => {
  await partyClient.post(`/${partyId}/leave`, { character_id: characterId });
};

export const disbandParty = async (partyId: number): Promise<void> => {
  await partyClient.delete(`/${partyId}`);
};

export const updateParty = async (
  partyId: number,
  patch: { name?: string; avatar?: string | null },
): Promise<Party> => {
  const { data } = await partyClient.patch(`/${partyId}`, patch);
  return data;
};

export const getPlayersOnLocation = async (
  locationId: number,
): Promise<PlayerOnLocation[]> => {
  const { data } = await charClient.get("/by_location", { params: { location_id: locationId } });
  return data ?? [];
};

export const getPartiesOnLocation = async (
  locationId: number,
): Promise<PartyOnLocation[]> => {
  const { data } = await partyClient.get("/by-location", { params: { location_id: locationId } });
  return data ?? [];
};

// Upload a squad avatar image and get its URL (reuses the generic photo-service
// image upload); the caller then saves it via updateParty.
export const uploadSquadAvatar = async (file: File): Promise<string> => {
  const form = new FormData();
  form.append("file", file);
  const { data } = await axios.post<{ image_url: string }>(
    "/photo/upload_archive_image",
    form,
    {
      headers: {
        "Content-Type": "multipart/form-data",
        Authorization: `Bearer ${localStorage.getItem("accessToken") || ""}`,
      },
    },
  );
  return data.image_url;
};
