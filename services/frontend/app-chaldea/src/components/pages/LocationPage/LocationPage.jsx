import s from "./LocationPage.module.scss";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { BASE_URL, BASE_URL_BATTLES } from "../../../api/api.js";
import axios from "axios";
import { useEffect, useState } from "react";
import { useBodyBackground } from "../../../hooks/useBodyBackground.js";
import Textarea from "../../CommonComponents/Textarea/Textarea.jsx";
import BlueGradientButton from "../../CommonComponents/BlueGradientButton/BlueGradientButton.jsx";
import PlayerCard from "../../CommonComponents/PlayerCard/PlayerCard.jsx";
import NeighborCard from "../../CommonComponents/NeighborCard/NeighborCard.jsx";
import Loader from "../../CommonComponents/Loader/Loader.jsx";
import { useSelector } from "react-redux";
import BackButton from "../../CommonComponents/BackButton/BackButton.jsx";

const DEFAULT_TAB = "players";

const LocationPage = () => {
  const navigate = useNavigate();
  const { locationId } = useParams();
  const [location, setLocation] = useState(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const [currentTab, setCurrentTab] = useState(
    searchParams.get("tab") || DEFAULT_TAB,
  );
  const [loading, setLoading] = useState(false);
  const [textareaValue, setTextareaValue] = useState("");
  const { character, username } = useSelector((state) => state.user);

  useBodyBackground(location?.image_url);

  useEffect(() => {
    if (locationId) {
      fetchLocationData();
    }
  }, [locationId]);

  useEffect(() => {
    const tab = searchParams.get("tab");
    setCurrentTab(tab || DEFAULT_TAB);
  }, [searchParams]);

  const handleTabChange = (tab) => {
    setCurrentTab(tab);
    setSearchParams({ tab });
  };

  const fetchLocationData = async () => {
    setLoading(true);
    const res = await axios.get(
      `${BASE_URL}/locations/${locationId}/client/details`,
    );
    setLocation(res.data);
    setLoading(false);
  };

  const handleSubmitPost = async () => {
    try {
      await axios.post(`${BASE_URL}/locations/${locationId}/move_and_post`, {
        character_id: character.id,
        location_id: locationId,
        content: textareaValue,
      });
      alert("пост отправлен");
      fetchLocationData();
      setTextareaValue("");
    } catch (error) {
      alert("ошибка пост не отправлен");
      console.log(error);
    }
  };

  const handleTextareaChange = (e) => {
    const { value } = e.target;
    setTextareaValue(value);
  };

  const handleClickCallengeToFightBtn = (opponentId) => {
    createBattle(opponentId);
    // const battleId = 123;
  };

  const createBattle = async (opponentId) => {
    try {
      const res = await axios.post(`${BASE_URL_BATTLES}/battles/`, {
        players: [{ character_id: opponentId }, { character_id: character.id }],
      });
      navigate(`battle/${res.data.battle_id}`);
      alert("битва началась");
    } catch (error) {
      alert("ошибка битва не началась");
      console.log(error);
    }
  };

  const renderTab = () => {
    switch (currentTab) {
      case "players":
        return (
          <div className={s.players_container}>
            {location.players.map((player, index) => (
              <PlayerCard
                name={player.character_name}
                price={player.character_title}
                img={player.character_photo}
                key={index}
              />
            ))}
          </div>
        );
      case "locations":
        return (
          <div className={s.neighbours_container}>
            {location.neighbors.map((neighbor, index) => (
              <NeighborCard
                name={neighbor.name}
                price={neighbor.energy_cost}
                img={neighbor.image_url}
                key={index}
                link={`/location/${neighbor.neighbor_id}`}
              />
            ))}
          </div>
        );
    }
  };

  return (
    location && (
      <div>
        <BackButton />
        {loading ? (
          <Loader />
        ) : (
          <div className={s.location_page}>
            <div className={s.content}>
              <div className={s.bar}>
                <div className={s.bar_top}>
                  <div
                    className={s.image}
                    style={{
                      backgroundImage: `url('${location?.image_url ? location?.image_url : ""}')`,
                    }}
                  ></div>
                  <span className={s.lvl}>
                    {location.recommended_level}+ LVL
                  </span>
                  <div className={s.buttons}>
                    <button
                      className={`${s.button} ${currentTab === "players" ? s.active : ""}`}
                      onClick={() => handleTabChange("players")}
                    >
                      Игроки
                    </button>
                    <button
                      className={`${s.button} ${currentTab === "locations" ? s.active : ""}`}
                      onClick={() => handleTabChange("locations")}
                    >
                      Переходы
                    </button>
                  </div>
                </div>
              </div>
              <div className={s.content_inner}>
                <h1>{location.name}</h1>
                <p>{location.description}</p>
                {renderTab()}
              </div>
            </div>

            <div className={s.textarea_container}>
              <Textarea
                value={textareaValue}
                onChange={handleTextareaChange}
                text="Введите текст..."
                name="post"
                id="post"
                cols="30"
                rows="10"
              ></Textarea>
              <BlueGradientButton onClick={handleSubmitPost} text="Отправить" />
            </div>

            {location.posts &&
              location.posts.map((post, index) => (
                <div className={s.post_container} key={index}>
                  <div className={s.post_author_container}>
                    <div className={s.author_inner}>
                      <div className={s.author_avatar_wrapper}>
                        <PlayerCard
                          name={post.character_name}
                          title={post.character_title}
                          img={post.character_photo}
                          key={index}
                        />
                        {/*<h4>{post.user_nickname}</h4>*/}
                      </div>

                      {post.user_nickname !== username && (
                        <div className={s.buttons}>
                          <button className={s.button}>Пожаловаться</button>
                          <button className={s.button}>Уведомить</button>
                          <button className={s.button}>Написать</button>
                          <button
                            onClick={() =>
                              handleClickCallengeToFightBtn(post.character_id)
                            }
                            className={s.button}
                          >
                            Вызвать на бой
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className={s.post}>
                    <p>{post.content}</p>
                    <div className={s.post_bottom}>
                      <span>Длина поста: {post.length}</span>
                    </div>
                  </div>
                </div>
              ))}
          </div>
        )}
      </div>
    )
  );
};

export default LocationPage;
