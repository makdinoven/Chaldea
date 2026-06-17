import CharacterSide from "./CharacterSide/CharacterSide";
import Loader from "../../CommonComponents/Loader/Loader";
import { useEffect, useState, useRef, useCallback } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import axios from "axios";

import toast from "react-hot-toast";
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
import { fetchBattleSpectateState } from "../../../api/battles";
import { checkActiveSession } from "../../../api/dungeons";
import useBattleWebSocket from "../../../hooks/useBattleWebSocket";

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
  is_paused?: boolean;
  paused_reason?: string | null;
  rewards?: BattleRewards | null;
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
  const location = useLocation();
  const { locationId, battleId } = useParams<{
    locationId: string;
    battleId: string;
  }>();
  const character = useAppSelector((state) => state.user.character);

  // Detect spectate mode from URL
  const isSpectateMode = location.pathname.endsWith("/spectate");

  const [battleResult, setBattleResult] = useState<BattleResultState | null>(
    null,
  );

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentTurn, setCurrentTurn] = useState<TurnInfo | null>(null);

  const [snapshotData, setSnapshotData] = useState<
    ParticipantSnapshot[] | null
  >(null);
  const [runtimeData, setRuntimeData] = useState<RuntimeState | null>(null);

  const [myData, setMyData] = useState<CharacterData>({});
  const [opponentData, setOpponentData] = useState<CharacterData | null>(null);
  // Group battles: every participant on the viewer's team / the enemy team(s).
  const [myTeamData, setMyTeamData] = useState<CharacterData[]>([]);
  const [enemyTeamData, setEnemyTeamData] = useState<CharacterData[]>([]);
  // Which enemy participant the next attack will hit.
  const [selectedTargetId, setSelectedTargetId] = useState<number | null>(null);

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

  // Navigate back: to dungeon session if in dungeon, otherwise to location
  const navigateAfterBattle = useCallback(() => {
    const charId = character?.id;
    const goToLocation = () => navigate(`/locations/${locationId}`);
    if (!charId) {
      goToLocation();
      return;
    }
    checkActiveSession(charId)
      .then((result) => {
        if (result.in_dungeon && result.session_id) {
          navigate(`/dungeon-session/${result.session_id}`);
        } else {
          goToLocation();
        }
      })
      .catch(goToLocation);
  }, [character?.id, locationId, navigate]);
  const battleResultSetRef = useRef(false);

  // Pause state
  const isPaused = runtimeData?.is_paused === true;

  // --- WebSocket integration ---
  const token = localStorage.getItem("accessToken");
  const {
    connected: wsConnected,
    reconnecting: wsReconnecting,
    fallbackToPolling,
    state: wsState,
    battleFinished: wsBattleFinished,
  } = useBattleWebSocket(battleId ?? "", token);

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

  // Process raw state (snapshot + runtime) into component state variables.
  // Group-battle aware: splits participants into the viewer's team and enemies.
  const processState = useCallback(
    (snapshot: ParticipantSnapshot[], runtime: RuntimeState) => {
      setSnapshotData(snapshot);
      setRuntimeData(runtime);
      setError(null);

      const teamOf = (pid: number) => runtime.participants[pid]?.team;
      const build = (p: ParticipantSnapshot): CharacterData => ({
        character_id: p.character_id,
        participant_id: p.participant_id,
        name: p.name,
        avatar: p.avatar,
        skills: p.skills,
        attributes: p.attributes,
        items: runtime.participants[p.participant_id]?.fast_slots,
        resources: getResources(p, runtime, p.participant_id),
      });

      // Viewer's own participant (participant mode). In spectate there is no
      // "me", so anchor the left side on the lowest team number.
      const mySnapshot = isSpectateMode
        ? undefined
        : snapshot.find((p) => p.character_id === character.id);
      if (!isSpectateMode && !mySnapshot) return;

      const viewerTeam = mySnapshot
        ? teamOf(mySnapshot.participant_id)
        : Math.min(...snapshot.map((p) => teamOf(p.participant_id) ?? 0));

      const myTeamSnaps = snapshot.filter(
        (p) => teamOf(p.participant_id) === viewerTeam,
      );
      const enemySnaps = snapshot.filter(
        (p) => teamOf(p.participant_id) !== viewerTeam,
      );

      // Viewer's own card comes first within their team.
      const orderedMyTeam = mySnapshot
        ? [
            mySnapshot,
            ...myTeamSnaps.filter(
              (p) => p.participant_id !== mySnapshot.participant_id,
            ),
          ]
        : myTeamSnaps;

      setMyTeamData(orderedMyTeam.map(build));
      setEnemyTeamData(enemySnaps.map(build));

      const ownSnap = mySnapshot ?? orderedMyTeam[0];
      setMyData(ownSnap ? build(ownSnap) : {});
      setOpponentData(enemySnaps.length ? build(enemySnaps[0]) : null);

      const now = Date.now();
      const turnEnd = new Date(runtime.deadline_at).getTime();
      const timeLeft = Math.max(0, turnEnd - now);
      const currentActorSnapshot = snapshot.find(
        (p) => p.participant_id === runtime.current_actor,
      );

      setCurrentTurn({
        currentCharacterParticipant: {
          id: runtime.current_actor,
          characterName: currentActorSnapshot?.name ?? "",
        },
        turn_number: runtime.turn_number,
        isOpponentTurn: isSpectateMode
          ? true
          : runtime.current_actor !== ownSnap?.participant_id,
        endsAt: timeLeft,
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [isSpectateMode, character],
  );

  // Process WS state updates
  useEffect(() => {
    if (!wsState) return;
    const snapshot = wsState.snapshot as unknown as ParticipantSnapshot[];
    const runtime = wsState.runtime as unknown as RuntimeState;
    processState(snapshot, runtime);
    setLoading(false);
  }, [wsState, processState]);

  // Handle WS battle_finished event
  useEffect(() => {
    if (!wsBattleFinished || battleResultSetRef.current) return;
    if (isSpectateMode) return; // Spectate detects finish via HP check

    // Determine winner from WS data
    // We need snapshot to find names — use current snapshotData
    if (!snapshotData || !runtimeData) return;

    const winnerTeam = wsBattleFinished.winner_team;

    const mySnapshot = snapshotData.find(
      (p) => p.character_id === character?.id,
    );
    if (!mySnapshot) return;

    const myPid = mySnapshot.participant_id;
    const myTeam = runtimeData.participants[myPid]?.team;
    const isLose = myTeam !== winnerTeam;

    const winnerSnapshot = snapshotData.find((p) => {
      const pid = p.participant_id;
      return runtimeData.participants[pid]?.team === winnerTeam;
    });

    battleResultSetRef.current = true;
    setBattleResult({
      winner: winnerSnapshot?.name ?? "",
      isLose,
    });

    // Handle rewards
    const rewards = wsBattleFinished.rewards;
    if (rewards && !isLose) {
      setPveRewards(rewards);
      setShowRewardsModal(true);
    }
  }, [wsBattleFinished, snapshotData, runtimeData, character, isSpectateMode]);

  const getBattleState = async (withLoading?: boolean) => {
    if (withLoading) {
      setLoading(true);
    }
    try {
      let snapshot: ParticipantSnapshot[];
      let runtime: RuntimeState;

      if (isSpectateMode) {
        const spectateData = await fetchBattleSpectateState(Number(battleId));
        snapshot = spectateData.snapshot;
        runtime = spectateData.runtime;
      } else {
        const { data } = await axios.get(
          `${BASE_URL_BATTLES}/battles/${battleId}/state`,
        );
        const response = data as {
          snapshot: ParticipantSnapshot[];
          runtime: RuntimeState;
        };
        snapshot = response.snapshot;
        runtime = response.runtime;
      }

      processState(snapshot, runtime);
    } catch (e) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } };
      const msg = err?.response?.data?.detail || "Не удалось загрузить состояние боя";
      setError(msg);
      if (!withLoading) {
        toast.error(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  // Polling: initial load + fallback when WS is not connected
  useEffect(() => {
    if (!isSpectateMode && !character) return;
    if (battleResult) return;

    // If WS is connected and not falling back to polling, skip polling entirely
    if (wsConnected && !fallbackToPolling) {
      // Still do initial load if we haven't loaded yet
      if (!snapshotData) {
        // WS will deliver initial state — just wait, but set loading false after a timeout
        // Actually, WS sends initial state on connect, so wsState effect will handle loading
      }
      return;
    }

    // If WS is reconnecting (not yet fallen back), don't start polling
    // The WS hook will either reconnect or set fallbackToPolling
    if (wsReconnecting && !fallbackToPolling) {
      // Do initial load if nothing loaded yet
      if (!snapshotData) {
        getBattleState(true);
      }
      return;
    }

    // Fallback polling mode OR initial load before WS connects
    const needsInitialLoad = !snapshotData;

    if (needsInitialLoad) {
      getBattleState(true);
    }

    // Only set up interval if fallback to polling is active OR WS hasn't connected yet
    if (fallbackToPolling || !wsConnected) {
      const intervalId = setInterval(() => {
        getBattleState();
      }, 5000);

      return () => clearInterval(intervalId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [battleId, character, battleResult, isSpectateMode, wsConnected, fallbackToPolling, wsReconnecting]);

  useEffect(() => {
    // Battle result detection (participant mode). Team-aware: a side loses only
    // when ALL of its members are down.
    if (isSpectateMode) return;
    if (battleResultSetRef.current) return;
    if (!runtimeData || myData.participant_id == null) return;

    const myTeam = runtimeData.participants[myData.participant_id]?.team;
    const all = Object.values(runtimeData.participants);
    const myTeamAlive = all.some((p) => p.team === myTeam && p.hp > 0);
    const enemyAlive = all.some((p) => p.team !== myTeam && p.hp > 0);

    if (!myTeamAlive) {
      battleResultSetRef.current = true;
      setBattleResult({ winner: opponentData?.name ?? "", isLose: true });
    } else if (!enemyAlive) {
      battleResultSetRef.current = true;
      setBattleResult({ winner: myData.name ?? "", isLose: false });
      const rewards = pveRewards ?? runtimeData?.rewards ?? null;
      if (rewards) {
        setPveRewards(rewards);
        setShowRewardsModal(true);
      }
    }
  }, [runtimeData, myData, opponentData, pveRewards, isSpectateMode]);

  // Keep a valid attack target selected: default to the first alive enemy and
  // reset if the current target dies or leaves.
  useEffect(() => {
    if (!runtimeData || isSpectateMode) return;
    const aliveEnemies = enemyTeamData.filter(
      (e) =>
        e.participant_id != null &&
        (runtimeData.participants[e.participant_id]?.hp ?? 0) > 0,
    );
    const stillValid =
      selectedTargetId != null &&
      aliveEnemies.some((e) => e.participant_id === selectedTargetId);
    if (!stillValid) {
      setSelectedTargetId(aliveEnemies[0]?.participant_id ?? null);
    }
  }, [enemyTeamData, runtimeData, selectedTargetId, isSpectateMode]);

  const handleSendTurn = async () => {
    if (!runtimeData || isSpectateMode || isPaused) return;
    const turnDataApi = {
      participant_id: myData.participant_id!,
      target_id: selectedTargetId,
      skills: {
        attack_skill_id: turnData.attack ? (turnData.attack as SkillSlot).id ?? null : null,
        defense_skill_id: turnData.defense ? (turnData.defense as SkillSlot).id ?? null : null,
        support_skill_id: turnData.support ? (turnData.support as SkillSlot).id ?? null : null,
        item_id: turnData.item ? (turnData.item as SkillSlot).item_id ?? null : null,
      },
    };

    const success = await setTurnApi(turnDataApi);

    if (success) {
      setTurnData({
        [SKILLS_KEYS.attack]: null,
        [SKILLS_KEYS.defense]: null,
        [SKILLS_KEYS.support]: null,
        [SKILLS_KEYS.item]: null,
      });
    }
  };

  const setTurnApi = async (actionData: unknown): Promise<boolean> => {
    try {
      const { data } = await axios.post<ActionResponseData>(
        `${BASE_URL_BATTLES}/battles/${battleId}/action`,
        actionData,
      );

      // Capture PvE rewards from action response
      if (data.battle_finished && data.rewards) {
        setPveRewards(data.rewards);
      }

      // If WS is connected, state will be pushed via WS; otherwise fetch manually
      if (!wsConnected) {
        getBattleState(false);
      }
      return true;
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } };
      const msg =
        err?.response?.data?.detail || "Ошибка при выполнении хода";
      toast.error(msg);
      return false;
    }
  };

  const toggleAutoBattle = async () => {
    if (isAutoBattleOn) {
      await postAutoBattleOff();
      setIsAutoBattleOn(false);
    } else {
      const success = await postAutoBattleOn();
      if (success) {
        setIsAutoBattleOn(true);
      }
    }
  };

  const postAutoBattleOn = async (): Promise<boolean> => {
    try {
      await axios.post(`${BASE_URL_AUTOBATTLES}/register`, {
        participant_id: myData.participant_id,
        battle_id: Number(battleId),
      });
      return true;
    } catch {
      toast.error("Не удалось включить автобой");
      return false;
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

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center gap-6 py-20">
        <p className="text-site-red text-xl">{error}</p>
        <BlueGradientButton
          onClick={() => navigateAfterBattle()}
          text="Вернуться на страницу локации"
        />
      </div>
    );
  }

  return (
    snapshotData &&
    runtimeData && (
      <div className="-mx-10">
        {/* WebSocket reconnection indicator */}
        {wsReconnecting && (
          <div className="flex items-center justify-center gap-2 mb-3 px-5 py-3 rounded-card shadow-card bg-gold-dark/90 text-white text-sm sm:text-base font-medium">
            <span className="inline-block w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
            Переподключение...
          </div>
        )}

        {/* Polling fallback indicator */}
        {fallbackToPolling && !wsConnected && (
          <div className="flex items-center justify-center gap-2 mb-3 px-5 py-3 rounded-card shadow-card bg-site-bg/90 text-white/80 text-sm sm:text-base border border-white/10">
            Используется резервное соединение
          </div>
        )}

        {/* Spectate mode banner */}
        {isSpectateMode && (
          <div className="gold-outline relative rounded-card mb-4 px-4 py-3 sm:px-6 sm:py-4 text-center">
            <p className="gold-text text-lg sm:text-xl font-medium uppercase relative z-10">
              Режим наблюдения
            </p>
          </div>
        )}

        {/* Pause banner */}
        {isPaused && (
          <div className="relative rounded-card mb-4 px-4 py-3 sm:px-6 sm:py-4 text-center bg-site-bg border border-gold-dark/50">
            <p className="text-gold text-sm sm:text-base font-medium">
              Бой приостановлен — рассматриваются заявки на присоединение
            </p>
          </div>
        )}

        <div className="grid grid-cols-[minmax(0,1fr)_240px_minmax(0,1fr)] sm:grid-cols-[minmax(0,1fr)_300px_minmax(0,1fr)] md:grid-cols-[minmax(0,1fr)_380px_minmax(0,1fr)] gap-2 sm:gap-4 text-white">
          {/* Viewer's team (own card first) */}
          <div className="flex flex-col gap-4 sm:gap-6">
            {myTeamData.map((c) => (
              <CharacterSide
                key={c.participant_id}
                characterData={c}
                isOpponent={false}
                setTurnData={
                  !isSpectateMode && c.participant_id === myData.participant_id
                    ? setTurnData
                    : undefined
                }
                runtimeData={runtimeData}
              />
            ))}
          </div>

          {!isSpectateMode && currentTurn && (
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
              isPaused={isPaused}
            />
          )}
          {isSpectateMode && currentTurn && (
            <div className="flex flex-col items-center gap-4 px-2 sm:px-4">
              <div className="text-center">
                <p className="text-white text-sm sm:text-base">
                  Ход: <span className="gold-text text-sm sm:text-base font-medium">{currentTurn.currentCharacterParticipant.characterName}</span>
                </p>
                <p className="text-white/60 text-xs sm:text-sm mt-1">
                  Ход {currentTurn.turn_number}
                </p>
              </div>
            </div>
          )}

          {/* Enemy team — tap a card to make it the attack target */}
          <div className="flex flex-col gap-4 sm:gap-6">
            {enemyTeamData.map((c) => {
              const pid = c.participant_id as number;
              const isDead = (runtimeData.participants[pid]?.hp ?? 0) <= 0;
              const isTarget = !isSpectateMode && selectedTargetId === pid;
              const selectable = !isSpectateMode && !isDead;
              return (
                <div
                  key={pid}
                  onClick={() => selectable && setSelectedTargetId(pid)}
                  className={`relative rounded-card transition-all duration-200 ${
                    selectable ? "cursor-pointer hover:opacity-90" : ""
                  } ${
                    isTarget
                      ? "ring-2 ring-site-red shadow-[0_0_16px_rgba(239,68,68,0.45)]"
                      : ""
                  } ${isDead ? "opacity-40 grayscale" : ""}`}
                >
                  {isTarget && (
                    <span className="absolute -top-2 right-2 z-10 rounded-full bg-site-red px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
                      Цель
                    </span>
                  )}
                  <CharacterSide
                    characterData={c}
                    isOpponent={true}
                    runtimeData={runtimeData}
                  />
                </div>
              );
            })}
          </div>

          {/* Battle result modal — standard win/lose (participant mode only) */}
          {!isSpectateMode && battleResult && !showRewardsModal && (
            <Modal>
              <div className="flex flex-col items-center gap-[30px]">
                <h2
                  className={
                    battleResult.isLose
                      ? "uppercase text-site-red text-3xl sm:text-[40px]"
                      : "gold-text text-3xl sm:text-[40px]"
                  }
                >
                  {battleResult.isLose ? "Поражение" : "Вы выиграли"}
                </h2>
                <p className="text-xl sm:text-2xl text-white">
                  Победитель: <span className="gold-text text-xl sm:text-2xl">{battleResult.winner}</span>
                </p>
                <BlueGradientButton
                  onClick={() => navigateAfterBattle()}
                  text={"Вернуться на страницу локации"}
                />
              </div>
            </Modal>
          )}

          {/* Spectate mode: show battle finished banner */}
          {isSpectateMode && snapshotData && runtimeData && (() => {
            // Check if any participant has 0 HP
            const deadParticipant = Object.entries(runtimeData.participants).find(
              ([, p]) => p.hp <= 0,
            );
            if (!deadParticipant) return null;

            return (
              <Modal>
                <div className="flex flex-col items-center gap-6 p-4 sm:p-6">
                  <h2 className="gold-text text-2xl sm:text-4xl font-medium uppercase">
                    Бой завершён
                  </h2>
                  <BlueGradientButton
                    onClick={() => navigateAfterBattle()}
                    text="Вернуться на страницу локации"
                  />
                </div>
              </Modal>
            );
          })()}

          {/* PvE rewards modal — shown on mob defeat with rewards (participant mode only) */}
          {!isSpectateMode && pveRewards && (
            <BattleRewardsModal
              rewards={pveRewards}
              visible={showRewardsModal}
              onClose={() => {
                setShowRewardsModal(false);
                navigateAfterBattle();
              }}
            />
          )}
        </div>
      </div>
    )
  );
};

export default BattlePage;
