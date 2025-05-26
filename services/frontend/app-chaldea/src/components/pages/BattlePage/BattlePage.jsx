import s from "./BattlePage.module.scss";
import CharacterSide from "./CharacterSide/CharacterSide.jsx";
import Loader from "../../CommonComponents/Loader/Loader.jsx";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useSelector } from "react-redux";
import axios from "axios";

import { useBodyBackground } from "../../../hooks/useBodyBackground.js";
import { BASE_URL_AUTOBATTLES, BASE_URL_BATTLES } from "../../../api/api.js";
import battleBg from "/battle-img-3.png";
import BattlePageBar from "./BattlePageBar/BattlePageBar.jsx";
import { SKILLS_KEYS } from "../../../helpers/commonConstants.js";
import Modal from "../../CommonComponents/Modal/Modal.jsx";
import BlueGradientButton from "../../CommonComponents/BlueGradientButton/BlueGradientButton.jsx";

const TURN_DURATION = 24 * 60 * 60 * 1000;

const BattlePage = () => {
  useBodyBackground(battleBg);
  const navigate = useNavigate();
  const { locationId, battleId } = useParams();
  const character = useSelector((state) => state.user.character);
  const [battleResult, setBattleResult] = useState(null);

  const [loading, setLoading] = useState(true);
  const [currentTurn, setCurrentTurn] = useState(null);

  const [snapshotData, setSnapshotData] = useState(null);
  const [runtimeData, setRuntimeData] = useState(null);

  const [myData, setMyData] = useState({});
  const [opponentData, setOpponentData] = useState(null);

  const [turnData, setTurnData] = useState({
    [SKILLS_KEYS.attack]: null,
    [SKILLS_KEYS.defense]: null,
    [SKILLS_KEYS.support]: null,
    [SKILLS_KEYS.item]: null,
  });

  const [isAutoBattleOn, setIsAutoBattleOn] = useState(false);
  const [autobattleMode, setAutobattleMode] = useState("balance");

  const getResources = (snapshot, runtime, id) => [
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

  const getBattleState = async (withLoading) => {
    if (withLoading) {
      setLoading(true);
    }
    try {
      const { data } = await axios.get(
        `${BASE_URL_BATTLES}/battles/${battleId}/state`,
      );
      const { snapshot, runtime } = data;

      setSnapshotData(snapshot);
      setRuntimeData(runtime);

      const mySnapshot = snapshot.find((p) => p.character_id === character.id);
      const oppSnapshot = snapshot.find((p) => p.character_id !== character.id);

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

      setCurrentTurn({
        currentCharacterParticipant: {
          id: runtime.next_actor,
          characterName: snapshot.find(
            (p) => p.participant_id === runtime.current_actor,
          ).name,
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

    getBattleState();

    return () => clearInterval(intervalId);
  }, [battleId, character]);

  useEffect(() => {
    if (opponentData && myData) {
      const oppHealth = opponentData.resources[0].health.current;
      const myHealth = myData.resources[0].health.current;

      if (myHealth <= 0) {
        setBattleResult({ winner: opponentData.name, isLose: true });
      } else if (oppHealth <= 0) {
        setBattleResult({ winner: myData.name, isLose: false });
      }
    }
  }, [opponentData, myData]);

  // useEffect(() => {
  //   console.log(runtimeData);
  // }, [runtimeData]);

  // useEffect(() => {
  //   console.log(snapshotData);
  // }, [snapshotData]);

  // useEffect(() => {
  //   console.log(opponentData);
  // }, [opponentData]);

  // useEffect(() => {
  //   console.log(currentTurn);
  // }, [currentTurn]);

  // useEffect(() => {
  //   console.log(turnData);
  // }, [turnData]);

  const handleSendTurn = async () => {
    const turnDataApi = {
      participant_id: runtimeData.current_actor,
      skills: {
        attack_rank_id: turnData.attack ? turnData.attack.id : null,
        defense_rank_id: turnData.defense ? turnData.defense.id : null,
        support_rank_id: turnData.support ? turnData.support.id : null,
        item_id: turnData.item ? turnData.item.item_id : null,
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

  const setTurnApi = async (turnData) => {
    try {
      await axios.post(
        `${BASE_URL_BATTLES}/battles/${battleId}/action`,
        turnData,
      );

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
    } catch (error) {}
  };

  const postAutoBattleOff = async () => {
    try {
      await axios.post(`${BASE_URL_AUTOBATTLES}/unregister`, {
        participant_id: myData.participant_id,
      });
    } catch (error) {}
  };

  const handleSetAutobattleMode = async () => {
    try {
      await axios.post(`${BASE_URL_AUTOBATTLES}/mode`, {
        mode: autobattleMode,
      });
    } catch (error) {}
  };

  useEffect(() => {
    if (isAutoBattleOn) {
      handleSetAutobattleMode();
    }
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
        {battleResult && (
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
      </div>
    )
  );
};

export default BattlePage;
