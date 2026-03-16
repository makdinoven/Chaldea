import React, { useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { BASE_URL, BASE_URL_BATTLES } from '../../../api/api';
import axios from 'axios';
import { useBodyBackground } from '../../../hooks/useBodyBackground';
import Textarea from '../../CommonComponents/Textarea/Textarea';
import BlueGradientButton from '../../CommonComponents/BlueGradientButton/BlueGradientButton';
import PlayerCard from '../../CommonComponents/PlayerCard/PlayerCard';
import NeighborCard from '../../CommonComponents/NeighborCard/NeighborCard';
import Loader from '../../CommonComponents/Loader/Loader';
import { useSelector } from 'react-redux';
import BackButton from '../../CommonComponents/BackButton/BackButton';

const DEFAULT_TAB = 'players';

interface Player {
  character_name: string;
  character_title: string;
  character_photo: string;
  character_id: number;
}

interface NeighborLocation {
  name: string;
  energy_cost: number;
  image_url: string;
  neighbor_id: number;
}

interface Post {
  character_name: string;
  character_title: string;
  character_photo: string;
  character_id: number;
  user_nickname: string;
  content: string;
  length: number;
}

interface LocationData {
  name: string;
  description: string;
  image_url: string | null;
  recommended_level: number;
  players: Player[];
  neighbors: NeighborLocation[];
  posts: Post[];
}

interface UserState {
  character: { id: number; current_location?: number } | null;
  username: string;
}

interface RootState {
  user: UserState;
}

const LocationPage = () => {
  const navigate = useNavigate();
  const { locationId } = useParams<{ locationId: string }>();
  const [location, setLocation] = useState<LocationData | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const [currentTab, setCurrentTab] = useState(
    searchParams.get('tab') || DEFAULT_TAB
  );
  const [loading, setLoading] = useState(false);
  const [textareaValue, setTextareaValue] = useState('');
  const { character, username } = useSelector(
    (state: RootState) => state.user
  );

  useBodyBackground(location?.image_url);

  useEffect(() => {
    if (locationId) {
      fetchLocationData();
    }
  }, [locationId]);

  useEffect(() => {
    const tab = searchParams.get('tab');
    setCurrentTab(tab || DEFAULT_TAB);
  }, [searchParams]);

  const handleTabChange = (tab: string) => {
    setCurrentTab(tab);
    setSearchParams({ tab });
  };

  const fetchLocationData = async () => {
    setLoading(true);
    const res = await axios.get(
      `${BASE_URL}/locations/${locationId}/client/details`
    );
    setLocation(res.data);
    setLoading(false);
  };

  const handleSubmitPost = async () => {
    try {
      await axios.post(`${BASE_URL}/locations/${locationId}/move_and_post`, {
        character_id: character?.id,
        location_id: locationId,
        content: textareaValue,
      });
      toast.success('Пост отправлен');
      fetchLocationData();
      setTextareaValue('');
    } catch (error) {
      toast.error('Не удалось отправить пост');
      console.log(error);
    }
  };

  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const { value } = e.target;
    setTextareaValue(value);
  };

  const handleClickCallengeToFightBtn = (opponentId: number) => {
    createBattle(opponentId);
  };

  const createBattle = async (opponentId: number) => {
    try {
      const res = await axios.post(`${BASE_URL_BATTLES}/battles/`, {
        players: [
          { character_id: opponentId },
          { character_id: character?.id },
        ],
      });
      navigate(`battle/${res.data.battle_id}`);
      toast.success('Битва началась!');
    } catch (error) {
      toast.error('Не удалось начать битву');
      console.log(error);
    }
  };

  const renderTab = () => {
    if (!location) return null;
    switch (currentTab) {
      case 'players':
        return (
          <div className="grid grid-cols-[repeat(5,188px)] gap-5">
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
      case 'locations':
        return (
          <div className="grid grid-cols-[repeat(5,179px)] gap-5">
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
      default:
        return null;
    }
  };

  return (
    location && (
      <div>
        <BackButton />
        {loading ? (
          <Loader />
        ) : (
          <div className="flex flex-col gap-[60px]">
            <div className="rounded-[15px] bg-[var(--gray-background)] flex gap-[65px] p-[35px] text-white w-full">
              <div className="flex justify-center min-w-[160px] w-[160px]">
                <div className="flex flex-col items-center gap-[30px]">
                  <div
                    className="relative min-w-[120px] w-[120px] h-[120px] m-1.5 bg-[#3d3d3d] rounded-full bg-center bg-no-repeat bg-cover gold-outline"
                    style={{
                      backgroundImage: `url('${location?.image_url ?? ''}')`,
                    }}
                  />
                  <span className="text-base uppercase bg-gradient-to-b from-[#fff9b8] to-[#bcab4c] bg-clip-text text-transparent">
                    {location.recommended_level}+ LVL
                  </span>
                  <div className="flex flex-col flex-1">
                    <button
                      className={`relative text-white font-medium text-xl py-[15px] hover:bg-gradient-to-b hover:from-[#fff9b8] hover:to-[#bcab4c] hover:bg-clip-text hover:text-transparent ${
                        currentTab === 'players'
                          ? 'uppercase bg-gradient-to-b from-[#fff9b8] to-[#bcab4c] bg-clip-text text-transparent'
                          : ''
                      }`}
                      onClick={() => handleTabChange('players')}
                    >
                      Игроки
                    </button>
                    <button
                      className={`relative text-white font-medium text-xl py-[15px] hover:bg-gradient-to-b hover:from-[#fff9b8] hover:to-[#bcab4c] hover:bg-clip-text hover:text-transparent ${
                        currentTab === 'locations'
                          ? 'uppercase bg-gradient-to-b from-[#fff9b8] to-[#bcab4c] bg-clip-text text-transparent'
                          : ''
                      }`}
                      onClick={() => handleTabChange('locations')}
                    >
                      Переходы
                    </button>
                  </div>
                </div>
              </div>
              <div className="flex flex-col gap-5">
                <h1 className="uppercase text-2xl bg-gradient-to-b from-[#fff9b8] to-[#bcab4c] bg-clip-text text-transparent">
                  {location.name}
                </h1>
                <p className="text-lg">{location.description}</p>
                {renderTab()}
              </div>
            </div>

            <div className="p-[35px] flex flex-col gap-[30px] rounded-[15px] bg-[var(--gray-background)]">
              <Textarea
                value={textareaValue}
                onChange={handleTextareaChange}
                text="Введите текст..."
                name="post"
                id="post"
                cols="30"
                rows="10"
              />
              <BlueGradientButton
                onClick={handleSubmitPost}
                text="Отправить"
              />
            </div>

            {location.posts &&
              location.posts.map((post, index) => (
                <div className="flex gap-5" key={index}>
                  <div className="min-w-[440px] w-[440px] p-10 flex flex-col gap-5 items-center rounded-[15px] bg-[var(--gray-background)] max-h-[428px]">
                    <div className="w-full flex gap-5">
                      <div className="flex flex-col items-center gap-5">
                        <PlayerCard
                          name={post.character_name}
                          title={post.character_title}
                          img={post.character_photo}
                          key={index}
                        />
                      </div>

                      {post.user_nickname !== username && (
                        <div className="flex flex-col flex-1">
                          <button className="relative text-white font-medium text-xl py-[15px]">
                            Пожаловаться
                          </button>
                          <button className="relative text-white font-medium text-xl py-[15px]">
                            Уведомить
                          </button>
                          <button className="relative text-white font-medium text-xl py-[15px]">
                            Написать
                          </button>
                          <button
                            onClick={() =>
                              handleClickCallengeToFightBtn(post.character_id)
                            }
                            className="relative text-white font-medium text-xl py-[15px]"
                          >
                            Вызвать на бой
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="rounded-[15px] bg-[var(--gray-background)] py-20 px-[60px] flex w-full flex-col justify-between text-white text-lg">
                    <p>{post.content}</p>
                    <div className="text-white text-xl">
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
