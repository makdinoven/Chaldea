import { useEffect, useState, useRef, useCallback } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import axios from "axios";
import toast from "react-hot-toast";
import { useBodyBackground } from "../../../../hooks/useBodyBackground";
import { useAppSelector } from "../../../../redux/store";
import { BASE_URL_BATTLES, postAutobattleMode } from "../../../../api/api";
import battleBg from "/battle-img-3.png";
import { SKILLS_KEYS } from "../../../../helpers/commonConstants";
import Modal from "../../../CommonComponents/Modal/Modal";
import BlueGradientButton from "../../../CommonComponents/BlueGradientButton/BlueGradientButton";
import BattleRewardsModal from "../BattleRewardsModal";
import useBattleWebSocket from "../../../../hooks/useBattleWebSocket";
import { evaluateControl, type EffectLike } from "../battleEffects";
import { parseServerDate } from "../../../../utils/serverDate";
import Battle3DArena from "./Battle3DArena";
import BattleLog from "./BattleLog";
import TurnInfo from "./TurnInfo";
import BattleSkillBar from "./BattleSkillBar";
import { checkActiveSession } from "../../../../api/dungeons";
import type {
  ResourceBlock,
  ParticipantSnapshot,
  RuntimeState,
  CharacterData,
  TurnInfo as TurnInfoType,
  SkillSlot,
  TurnDataState,
  BattleResultState,
} from "../battleTypes";
import type { BattleRewards } from "../../../../api/mobs";

interface BattleLogEntry {
  id: string;
  timestamp: number;
  message: string;
  type: "damage" | "heal" | "buff" | "debuff" | "special" | "system";
  actor?: string;
  value?: number;
}

const Battle3DPage = () => {
  console.log("[3DBattle] Component mounted");
  useBodyBackground(battleBg);
  const navigate = useNavigate();
  const location = useLocation();
  const { locationId, battleId } = useParams<{
    locationId: string;
    battleId: string;
  }>();
  console.log("[3DBattle] Params:", { locationId, battleId });
  const character = useAppSelector((state) => state.user.character);

  const isSpectateMode = location.pathname.endsWith("/spectate");

  // State
  const [battleResult, setBattleResult] = useState<BattleResultState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentTurn, setCurrentTurn] = useState<TurnInfoType | null>(null);

  const [snapshotData, setSnapshotData] = useState<ParticipantSnapshot[] | null>(null);
  const [runtimeData, setRuntimeData] = useState<RuntimeState | null>(null);

  const [myData, setMyData] = useState<CharacterData>({});
  const [myTeamData, setMyTeamData] = useState<CharacterData[]>([]);
  const [enemyTeamData, setEnemyTeamData] = useState<CharacterData[]>([]);

  const [selectedTargetId, setSelectedTargetId] = useState<number | null>(null);
  const [selectedAllyId, setSelectedAllyId] = useState<number | null>(null);

  const [turnData, setTurnData] = useState<TurnDataState>({
    [SKILLS_KEYS.attack]: null,
    [SKILLS_KEYS.defense]: null,
    [SKILLS_KEYS.support]: null,
    [SKILLS_KEYS.item]: null,
  });

  const [isAutoBattleOn, setIsAutoBattleOn] = useState(false);
  const [autobattleMode, setAutobattleMode] = useState("balance");
  const [pveRewards, setPveRewards] = useState<BattleRewards | null>(null);
  const [showRewardsModal, setShowRewardsModal] = useState(false);

  // Логи боя для UI
  const [battleLogs, setBattleLogs] = useState<BattleLogEntry[]>([]);
  const logIdRef = useRef(0);

  const navigateAfterBattle = useCallback(() => {
    const charId = character?.id;
    const goToLocation = () => navigate(`/location/${locationId}`);
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
  const isPaused = runtimeData?.is_paused === true;

  const isMyTurn = currentTurn ? !currentTurn.isOpponentTurn : false;
  const myControl =
    !isSpectateMode && isMyTurn && myData.participant_id != null
      ? evaluateControl(runtimeData?.active_effects?.[myData.participant_id])
      : { fullSkip: null as string | null, blocked: [] as string[] };

  // WebSocket
  const token = localStorage.getItem("accessToken");
  const { connected: wsConnected, state: wsState, battleFinished: wsBattleFinished } = useBattleWebSocket(battleId ?? "", token);

  const getResources = (snapshot: ParticipantSnapshot, runtime: RuntimeState, id: number): ResourceBlock[] => [
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
      energy: {
        current: runtime.participants[id].energy,
        max: snapshot.attributes.max_energy,
      },
    },
  ];

  // Обработка состояния боя (синхронизация teams)
  const processState = useCallback(
    (snapshot: ParticipantSnapshot[], runtime: RuntimeState) => {
      setSnapshotData(snapshot);
      setRuntimeData(runtime);
      setError(null);

      console.log("[3DBattle] Processing state with snapshot:", {
        participantCount: snapshot.length,
        avatarData: snapshot.map(p => ({ name: p.name, avatar: p.avatar, char_id: p.character_id }))
      });

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
        title: p.name,
      });

      const mySnapshot = isSpectateMode
        ? undefined
        : snapshot.find((p) => p.character_id === character.id);
      if (!isSpectateMode && !mySnapshot) return;

      const viewerTeam = mySnapshot
        ? teamOf(mySnapshot.participant_id)
        : Math.min(...snapshot.map((p) => teamOf(p.participant_id) ?? 0));

      const myTeamSnaps = snapshot.filter(
        (p) => teamOf(p.participant_id) === viewerTeam
      );
      const enemySnaps = snapshot.filter(
        (p) => teamOf(p.participant_id) !== viewerTeam
      );

      const orderedMyTeam = mySnapshot
        ? [
            mySnapshot,
            ...myTeamSnaps.filter((p) => p.participant_id !== mySnapshot.participant_id),
          ]
        : myTeamSnaps;

      setMyTeamData(orderedMyTeam.map(build));
      setEnemyTeamData(enemySnaps.map(build));

      const ownSnap = mySnapshot ?? orderedMyTeam[0];
      setMyData(ownSnap ? build(ownSnap) : {});

      const now = Date.now();
      const turnEnd = parseServerDate(runtime.deadline_at);
      const timeLeft = turnEnd ? Math.max(0, turnEnd.getTime() - now) : 0;
      const currentActorSnapshot = snapshot.find(
        (p) => p.participant_id === runtime.current_actor
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
    [isSpectateMode, character]
  );

  // Wait for WebSocket to connect and receive initial state
  useEffect(() => {
    if (wsConnected && wsState && "runtime" in wsState && "snapshot" in wsState) {
      processState(wsState.snapshot as ParticipantSnapshot[], wsState.runtime as RuntimeState);
      setLoading(false);
      addBattleLog("Бой начался", "system");
    } else if (battleId && !wsConnected) {
      setLoading(true);
    }
  }, [wsConnected, wsState, battleId]);

  // Обновление состояния при изменении WebSocket
  useEffect(() => {
    if (wsState && snapshotData && "runtime" in wsState) {
      const runtimeState = wsState.runtime;
      processState(snapshotData, runtimeState as RuntimeState);

      // Логирование событий
      if (runtimeState.turn_number !== currentTurn?.turn_number) {
        const newActor = snapshotData.find((p) => p.participant_id === runtimeState.current_actor);
        if (newActor) {
          addBattleLog(`${newActor.name} начинает ход`, "system");
        }
      }
    }
  }, [wsState, snapshotData]);

  // Проверка завершения боя
  useEffect(() => {
    if (!isSpectateMode && wsBattleFinished && !battleResultSetRef.current && runtimeData) {
      battleResultSetRef.current = true;

      const winnerParticipant = snapshotData?.find(
        (p) => p.participant_id === wsBattleFinished.winner_team
      );
      const isLose = character?.id !== wsBattleFinished.winner_team;

      setBattleResult({
        winner: winnerParticipant?.name || "Неизвестный",
        isLose,
      });

      if (wsBattleFinished.rewards) {
        setPveRewards(wsBattleFinished.rewards);
        setShowRewardsModal(true);
      }

      addBattleLog(isLose ? "Вы проиграли" : "Вы выиграли", "system");
    }
  }, [wsBattleFinished, isSpectateMode, character?.id, snapshotData, runtimeData]);

  // Добавление лога
  const addBattleLog = (message: string, type: BattleLogEntry["type"], value?: number) => {
    setBattleLogs((prev) => [
      ...prev,
      {
        id: `log-${logIdRef.current++}`,
        timestamp: Date.now(),
        message,
        type,
        value,
      },
    ]);
  };

  // Отправка хода
  const handleSendTurn = async (selectedSkill: any) => {
    if (!battleId || !myData.participant_id) return;

    try {
      const payload = {
        skill_type: selectedSkill.type,
        skill_id: selectedSkill.id,
        item_id: selectedSkill.item_id,
        target_participant_id: selectedTargetId,
      };

      const response = await axios.post(
        `${BASE_URL_BATTLES}/battles/${battleId}/turn`,
        payload,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      addBattleLog(`${myData.name} использовал ${selectedSkill.name}`, selectedSkill.type);

      // Сброс выбора
      setTurnData({
        [SKILLS_KEYS.attack]: null,
        [SKILLS_KEYS.defense]: null,
        [SKILLS_KEYS.support]: null,
        [SKILLS_KEYS.item]: null,
      });
    } catch (err) {
      toast.error("Ошибка отправки хода");
    }
  };

  // Переключение автобоя
  const toggleAutoBattle = async () => {
    try {
      if (myData.participant_id) {
        await postAutobattleMode(myData.participant_id, autobattleMode);
        setIsAutoBattleOn(!isAutoBattleOn);
        addBattleLog(
          `Автобой ${!isAutoBattleOn ? "включен" : "отключен"}`,
          "system"
        );
      }
    } catch {
      toast.error("Ошибка переключения автобоя");
    }
  };

  useEffect(() => {
    console.log("[3DBattle] loading:", loading, "wsConnected:", wsConnected, "snapshotData:", !!snapshotData, "runtimeData:", !!runtimeData);
  }, [loading, wsConnected, snapshotData, runtimeData]);

  if (loading) return <div className="text-white text-center py-20">Загрузка боя...</div>;
  if (error) return <div className="text-red-400 text-center py-20">Ошибка: {error}</div>;
  if (!snapshotData || !runtimeData) return <div className="text-white text-center py-20">Ожидание данных боя...</div>;

  return (
    <div className="fixed inset-0 w-screen h-screen bg-black overflow-hidden">
      {/* 3D ARENA - заполняет весь экран */}
      {snapshotData && runtimeData && (
        <div className="absolute inset-0">
          <Battle3DArena
            myTeamData={myTeamData}
            enemyTeamData={enemyTeamData}
            currentActorId={runtimeData.current_actor}
            selectedTargetId={selectedTargetId}
            onCardClick={(participantId, isEnemy) => {
              if (isEnemy) {
                setSelectedTargetId(participantId);
              }
            }}
          />
        </div>
      )}

      {/* Переключатель 2D/3D (сверху по центру) */}
      <div className="absolute top-4 left-1/2 transform -translate-x-1/2 z-50 flex gap-2">
        <button
          onClick={() => navigate(`/location/${locationId}/battle/${battleId}`)}
          className="px-4 py-2 rounded-lg bg-gray-700/50 hover:bg-gray-600/50 text-white text-sm font-semibold transition-all"
        >
          2D версия
        </button>
        <button
          disabled
          className="px-4 py-2 rounded-lg bg-gold/30 text-white text-sm font-semibold"
        >
          3D версия
        </button>
      </div>

      {/* BATTLE LOG (левый угол) */}
      <div className="absolute top-0 left-0 z-40 pointer-events-auto">
        <BattleLog logs={battleLogs} />
      </div>

      {/* TURN INFO (правый угол) */}
      {currentTurn && (
        <div className="absolute top-0 right-0 z-40 pointer-events-auto">
          <TurnInfo
            currentCharacterName={currentTurn.currentCharacterParticipant.characterName}
            turnNumber={currentTurn.turn_number}
            totalTurns={runtimeData?.total_turns || 0}
            timeLeft={currentTurn.endsAt - Date.now() / 1000}
            isMyTurn={isMyTurn}
            isAutoBattle={isAutoBattleOn}
            onToggleAutoBattle={toggleAutoBattle}
            onMakeTurn={() => {
              if (turnData[SKILLS_KEYS.attack]) {
                handleSendTurn(turnData[SKILLS_KEYS.attack]);
              }
            }}
            energy={myData.resources?.[2]?.energy?.current || 0}
            maxEnergy={myData.resources?.[2]?.energy?.max || 100}
            isPaused={isPaused}
          />
        </div>
      )}

      {/* SKILL BAR (внизу) */}
      <div className="absolute bottom-0 left-0 right-0 z-40 pointer-events-auto">
        <BattleSkillBar
          selectedSkills={turnData}
          onSkillSelect={(type) => {
            addBattleLog(`Выбран ${type}`, "system");
          }}
          isMyTurn={isMyTurn}
          controlFullSkip={myControl.fullSkip}
          blockedSkills={myControl.blocked}
        />
      </div>

      {/* Модали */}
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
            <BlueGradientButton text="Вернуться" onClick={navigateAfterBattle} />
          </div>
        </Modal>
      )}

      {pveRewards && (
        <BattleRewardsModal
          rewards={pveRewards}
          visible={showRewardsModal}
          onClose={navigateAfterBattle}
        />
      )}
    </div>
  );
};

export default Battle3DPage;
