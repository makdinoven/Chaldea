import { useRef, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useSelector } from 'react-redux';
import useNavigateTo from '../../../hooks/useNavigateTo';
import CharacterInfo from './CharacterInfo/CharacterInfo';
import CharacterInfoSmall from './CharacterInfoSmall/CharacterInfoSmall';
import defaultAvatar from '../../../assets/menu2.png';

interface Biography {
  biography: string;
  personality: string;
  appearance: string;
  name: string;
  age: string;
  height: string;
  weight: string;
  background: string;
  sex: string;
}

interface SubmitPageProps {
  biography: Biography;
  selectedRace: string;
  selectedRaceId: number;
  selectedSubrace: string;
  selectedSubraceId: number | null;
  selectedClass: string;
  selectedClassId: number;
}

interface UserState {
  id: number;
}

export default function SubmitPage({
  biography,
  selectedRace,
  selectedRaceId,
  selectedSubrace,
  selectedSubraceId,
  selectedClass,
  selectedClassId,
}: SubmitPageProps) {
  const { id } = useSelector((state: { user: UserState }) => state.user);

  const navigateTo = useNavigateTo();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [avatarUrl, setAvatarUrl] = useState<string>(defaultAvatar);
  const [submitting, setSubmitting] = useState(false);

  const handlePhotoInputClick = () => {
    fileInputRef.current?.click();
  };

  const handleSubmit = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();

    const data = {
      ...biography,
      user_id: id,
      avatar: 'string',
      id_subrace: selectedSubraceId,
      id_class: selectedClassId,
      id_race: selectedRaceId,
    };

    setSubmitting(true);

    axios
      .post('/characters/requests/', data)
      .then((response) => {
        if (response.status === 200) {
          toast.success('Заявка успешно подана');
          navigateTo('/home');
        }
      })
      .catch(() => {
        toast.error('Ошибка при подаче заявки');
      })
      .finally(() => {
        setSubmitting(false);
      });
  };

  const sendPhoto = () => {
    const file = fileInputRef.current?.files?.[0];
    const user_id = 1;

    if (!file) {
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('user_id', String(user_id));

    axios
      .post('/photo/character_avatar_preview', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })
      .then((response) => {
        const { avatar_url } = response.data;
        setAvatarUrl(avatar_url);
      })
      .catch(() => {
        toast.error('Ошибка загрузки фото');
      });
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      sendPhoto();
    }
  };

  const biographyItems = [
    { title: 'Биография', text: biography.biography },
    { title: 'Личность', text: biography.personality },
    { title: 'Внешность', text: biography.appearance },
  ];

  const characterItemsSmall = [
    { text: `${selectedRace} - ${selectedSubrace}` },
    { text: selectedClass },
    { text: biography.age ? `Возраст : ${biography.age}` : null },
    { text: biography.height ? `Рост : ${biography.height}` : null },
    { text: biography.sex ? `Пол : ${biography.sex}` : null },
    { text: biography.background || null },
  ];

  return (
    <>
      <div className="grid grid-cols-[1fr_3fr] gap-x-[90px] w-full h-full px-[120px] mb-[70px]">
        {/* Left column: avatar + small info */}
        <div>
          <div
            className="relative w-[214px] h-[214px] cursor-pointer bg-cover bg-no-repeat rounded-[16px] mb-[65px]"
            onClick={handlePhotoInputClick}
            style={{ backgroundImage: `url(${avatarUrl})` }}
          >
            {/* Dark overlay */}
            <div className="absolute inset-0 bg-black/20 rounded-[16px]" />

            {/* Character name at bottom */}
            <div className="absolute bottom-0 left-0 w-full h-[70px] flex items-center justify-center bg-gradient-to-t from-[rgba(28,26,26,0.9)] to-transparent rounded-b-[15px]">
              <span className="font-medium text-sm uppercase text-center text-gold">
                {biography.name}
              </span>
            </div>

            {/* Change avatar label */}
            <label
              htmlFor="fileInput"
              className="absolute bottom-[-30px] left-1/2 -translate-x-1/2 w-[140%] text-center text-base font-normal tracking-[-0.03em] gold-text cursor-pointer"
            >
              Сменить аватар
            </label>
            <input
              className="hidden"
              onChange={handleFileChange}
              ref={fileInputRef}
              type="file"
              id="fileInput"
              accept="image/*"
            />
          </div>

          {/* Small info items with top gradient divider */}
          <div className="relative before:content-[''] before:absolute before:top-0 before:left-1/2 before:-translate-x-1/2 before:w-full before:h-px before:bg-gradient-to-r before:from-transparent before:via-[#999] before:to-transparent before:z-[1]">
            {characterItemsSmall.map(
              (item, index) =>
                item.text && (
                  <CharacterInfoSmall
                    key={index}
                    text={item.text}
                  />
                )
            )}
          </div>
        </div>

        {/* Right column: biography sections */}
        <div className="flex flex-col gap-10">
          {biographyItems.map((item, index) => (
            <CharacterInfo key={index} title={item.title} text={item.text} />
          ))}
        </div>
      </div>

      {/* Submit button */}
      <div className="flex justify-center">
        <button
          className="btn-blue"
          onClick={handleSubmit}
          disabled={submitting}
        >
          {submitting ? 'Отправка...' : 'Отправить анкету'}
        </button>
      </div>
    </>
  );
}
