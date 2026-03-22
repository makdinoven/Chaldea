import s from "./BattlePage.module.scss";
import CharacterSide from "./CharacterSide/CharacterSide";
import Loader from "../../CommonComponents/Loader/Loader";
import { useEffect, useState, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import axios from "axios";

import { useBodyBackground } from "../../../hooks/useBodyBackground";
import { useAppSelector } from "../../../redux/store";
import { BASE_URL_AUTOBATTLES, BASE_URL_BATTLES } from "../../../api/api";
import battleBg from "/battle-img-3.png";
import BattlePageBar from "./BattlePageBar/BattlePageBar";
import { SKILLS_KEYS } from "../../../helpers/commonConstants";
import Modal from "../../CommonComponents/Modal/Modal";
import BlueGradientButton from "../../CommonComponents/BlueGradientButton/BlueGradientButton";
import BattleRewardsModal from "./BattleRewardsModal";
import type { BattleRewards } from "../../../api/mobs";

// --- Types ---

interface ResourceEntry {
  current: number;
  max: number;
}

interface ResourceBlock {
  health?: ResourceEntry;
  mana?: ResourceEntry;
  stamina?: ResourceEntry;
  energy?: ResourceEntry;
}

// TODO: type these properly when sub-components are migrated to TS
interface ParticipantSnapshot {
  participant_id: number;
  character_id: number;
  name: string;
  avatar: string | null;
  skills: unknown;
  attributes: Record<string, number>;
}

interface RuntimeState {
  participants: Record<
    number,
    {
      hp: number;
      mana: number;
      stamina: number;
      energy: number;
      fast_slots: unknown;
      team: number;
    }
  >;
  current_actor: number;
  next_actor: number;
  turn_number: number;
  turn_order: number[];
  total_turns: number;
  first_actor: number;
  deadline_at: string;
}

interface CharacterData {
  character_id?: number;
  participant_id?: number;
  name?: string;
  avatar?: string | null;
  skills?: unknown;
  attributes?: Record<string, number>;
  items?: unknown;
  resources?: ResourceBlock[];
}

interface TurnInfo {
  currentCharacterParticipant: {
    id: number;
    characterName: string;
  };
  turn_number: number;
  isOpponentTurn: boolean;
  endsAt: number;
}

interface SkillSlot {
  id?: number;
  item_id?: number;
}

interface TurnDataState {
  [key: string]: SkillSlot | null;
}

interface BattleResultState {
  winner: string;
  isLose: boolean;
}

interface ActionResponseData {
  ok: boolean;
  turn_number: number;
  next_actor: number;
  deadline_at: string;
  events: unknown[];
  battle_finished?: boolean;
  winner_team?: number;
  rewards?: BattleRewards;
}

// --- Component ---

const BattlePage = () => {
  useBodyBackground(battleBg);
  const navigate = useNavigate();
  const { locationId, battleId } = useParams<{
    locationId: string;
    battleId: string;
  }>();
  const character = useAppSelector((state) => state.user.character);
  const [battleResult, setBattleResult] = useState<BattleResultState | null>(
    null,
  );

  const [loading, setLoading] = useState(true);
  const [currentTurn, setCurrentTurn] = useState<TurnInfo | null>(null);

  const [snapshotData, setSnapshotData] = useState<
    ParticipantSnapshot[] | null
  >(null);
  const [runtimeData, setRuntimeData] = useState<RuntimeState | null>(null);

  const [myData, setMyData] = useState<CharacterData>({});
  const [opponentData, setOpponentData] = useState<CharacterData | null>(null);

  const [turnData, setTurnData] = useState<TurnDataState>({
    [SKILLS_KEYS.attack]: null,
    [SKILLS_KEYS.defense]: null,
    [SKILLS_KEYS.support]: null,
    [SKILLS_KEYS.item]: null,
  });

  const [isAutoBattleOn, setIsAutoBattleOn] = useState(false);
  const [autobattleMode, setAutobattleMode] = useState("balance");

  // PvE rewards state
  const [pveRewards, setPveRewards] = useState<BattleRewards | null>(null);
  const [showRewardsModal, setShowRewardsModal] = useState(false);
  const battleResultSetRef = useRef(false);

  const getResources = (
    snapshot: ParticipantSnapshot,
    runtime: RuntimeState,
    id: number,
  ): ResourceBlock[] => [
    {
      health: {
        current: runtime.participants[id].hp,
        max: snapshot.attributes.max_health,
      },
    },
    {
      mana: {
        current: runtime.participants[id].mana,
        max: snapshot.attributes.max_mana,
      },
    },
    {
      stamina: {
        current: runtime.participants[id].stamina,
        max: snapshot.attributes.max_stamina,
      },
    },
    {
      energy: {
        current: runtime.participants[id].energy,
        max: snapshot.attributes.max_energy,
      },
    },
  ];

  const getBattleState = async (withLoading?: boolean) => {
    if (withLoading) {
      setLoading(true);
    }
    try {
      const { data } = await axios.get(
        `${BASE_URL_BATTLES}/battles/${battleId}/state`,
      );
      const { snapshot, runtime } = data as {
        snapshot: ParticipantSnapshot[];
        runtime: RuntimeState;
      };

      setSnapshotData(snapshot);
      setRuntimeData(runtime);

      const mySnapshot = snapshot.find(
        (p: ParticipantSnapshot) => p.character_id === character.id,
      );
      const oppSnapshot = snapshot.find(
        (p: ParticipantSnapshot) => p.character_id !== character.id,
      );

      if (!mySnapshot || !oppSnapshot) return;

      const myParticipantId = mySnapshot.participant_id;
      const oppParticipantId = oppSnapshot.participant_id;

      setMyData({
        character_id: character.id,
        participant_id: myParticipantId,
        name: mySnapshot.name,
        avatar: mySnapshot.avatar,
        skills: mySnapshot.skills,
        attributes: mySnapshot.attributes,
        items: runtime.participants[myParticipantId].fast_slots,
        resources: getResources(mySnapshot, runtime, myParticipantId),
      });

      setOpponentData({
        character_id: oppSnapshot.character_id,
        participant_id: oppParticipantId,
        name: oppSnapshot.name,
        avatar: oppSnapshot.avatar,
        skills: oppSnapshot.skills,
        attributes: oppSnapshot.attributes,
        items: runtime.participants[oppParticipantId].fast_slots,
        resources: getResources(oppSnapshot, runtime, oppParticipantId),
      });

      const now = Date.now();
      const turnEnd = new Date(runtime.deadline_at).getTime();
      const timeLeft = Math.max(0, turnEnd - now);

      const currentActorSnapshot = snapshot.find(
        (p: ParticipantSnapshot) =>
          p.participant_id === runtime.current_actor,
      );

      setCurrentTurn({
        currentCharacterParticipant: {
          id: runtime.current_actor,
          characterName: currentActorSnapshot?.name ?? "",
        },
        turn_number: runtime.turn_number,
        isOpponentTurn: runtime.current_actor !== myParticipantId,
        endsAt: timeLeft,
      });
    } catch (error) {
      console.error("Failed to load battle state:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!character) return;
    if (battleResult) return;

    const intervalId = setInterval(() => {
      getBattleState();
    }, 5000);

    getBattleState(true);

    return () => clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [battleId, character, battleResult]);

  useEffect(() => {
    if (battleResultSetRef.current) return;
    if (opponentData?.resources && myData?.resources) {
      const oppHealth = (opponentData.resources[0] as { health: ResourceEntry })
        .health.current;
      const myHealth = (myData.resources[0] as { health: ResourceEntry }).health
        .current;

      if (myHealth <= 0) {
        battleResultSetRef.current = true;
        setBattleResult({ winner: opponentData.name ?? "", isLose: true });
      } else if (oppHealth <= 0) {
        battleResultSetRef.current = true;
        setBattleResult({ winner: myData.name ?? "", isLose: false });
        // Show rewards modal if we have PvE rewards
        if (pveRewards) {
          setShowRewardsModal(true);
        }
      }
    }
  }, [opponentData, myData, pveRewards]);

  const handleSendTurn = async () => {
    if (!runtimeData) return;
    const turnDataApi = {
      participant_id: myData.participant_id!,
      skills: {
        attack_rank_id: turnData.attack ? (turnData.attack as SkillSlot).id ?? null : null,
        defense_rank_id: turnData.defense ? (turnData.defense as SkillSlot).id ?? null : null,
        support_rank_id: turnData.support ? (turnData.support as SkillSlot).id ?? null : null,
        item_id: turnData.item ? (turnData.item as SkillSlot).item_id ?? null : null,
      },
    };

    await setTurnApi(turnDataApi);

    setTurnData({
      [SKILLS_KEYS.attack]: null,
      [SKILLS_KEYS.defense]: null,
      [SKILLS_KEYS.support]: null,
      [SKILLS_KEYS.item]: null,
    });
  };

  const setTurnApi = async (actionData: unknown) => {
    try {
      const { data } = await axios.post<ActionResponseData>(
        `${BASE_URL_BATTLES}/battles/${battleId}/action`,
        actionData,
      );

      // Capture PvE rewards from action response
      if (data.battle_finished && data.rewards) {
        setPveRewards(data.rewards);
      }

      getBattleState(false);
    } catch (e) {
      console.error(e);
    }
  };

  const toggleAutoBattle = async () => {
    if (isAutoBattleOn) {
      await postAutoBattleOff();
    } else {
      await postAutoBattleOn();
    }

    setIsAutoBattleOn((prev) => !prev);
  };

  const postAutoBattleOn = async () => {
    try {
      await axios.post(`${BASE_URL_AUTOBATTLES}/register`, {
        participant_id: myData.participant_id,
        battle_id: Number(battleId),
      });
    } catch {
      // silently handled — autobattle is optional
    }
  };

  const postAutoBattleOff = async () => {
    try {
      await axios.post(`${BASE_URL_AUTOBATTLES}/unregister`, {
        participant_id: myData.participant_id,
      });
    } catch {
      // silently handled — autobattle is optional
    }
  };

  const handleSetAutobattleMode = async () => {
    try {
      await axios.post(`${BASE_URL_AUTOBATTLES}/mode`, {
        mode: autobattleMode,
      });
    } catch {
      // silently handled — autobattle is optional
    }
  };

  useEffect(() => {
    if (isAutoBattleOn) {
      handleSetAutobattleMode();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autobattleMode, isAutoBattleOn]);

  if (loading) return <Loader />;

  return (
    snapshotData &&
    runtimeData && (
      <div className={s.battlePage_container}>
        <CharacterSide
          characterData={myData}
          isOpponent={false}
          setTurnData={setTurnData}
          runtimeData={runtimeData}
        />
        <BattlePageBar
          battleId={battleId}
          myData={myData}
          opponentData={opponentData}
          turnData={turnData}
          setTurnData={setTurnData}
          turn={currentTurn}
          setTurn={handleSendTurn}
          isAutoBattleOn={isAutoBattleOn}
          setAutobattleMode={setAutobattleMode}
          autobattleMode={autobattleMode}
          toggleAutobattle={toggleAutoBattle}
          snapshotData={snapshotData}
          runtimeData={runtimeData}
        />
        <CharacterSide
          runtimeData={runtimeData}
          characterData={opponentData}
          isOpponent={true}
        />

        {/* Battle result modal — standard win/lose */}
        {battleResult && !showRewardsModal && (
          <Modal>
            <div className={s.modal_container}>
              <h2 className={`${battleResult.isLose ? s.lose : s.win}`}>
                {battleResult.isLose ? "Поражение" : "Вы выиграли"}
              </h2>
              <p>
                Победитель: <span>{battleResult.winner}</span>
              </p>
              <BlueGradientButton
                onClick={() => navigate(`/location/${locationId}`)}
                text={"Вернуться на страницу локации"}
              />
            </div>
          </Modal>
        )}

        {/* PvE rewards modal — shown on mob defeat with rewards */}
        {pveRewards && (
          <BattleRewardsModal
            rewards={pveRewards}
            visible={showRewardsModal}
            onClose={() => {
              setShowRewardsModal(false);
              navigate(`/location/${locationId}`);
            }}
          />
        )}
      </div>
    )
  );
};

export default BattlePage;
