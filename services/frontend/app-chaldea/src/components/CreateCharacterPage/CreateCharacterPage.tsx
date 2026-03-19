import { useEffect, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import useNavigateTo from '../../hooks/useNavigateTo';
import { useRequireAuth } from '../../hooks/useRequireAuth';

import RacePage from './RacePage/RacePage';
import ClassPage from './ClassPage/ClassPage';
import BiographyPage from './BiographyPage/BiographyPage';
import SubmitPage from './SubmitPage/SubmitPage';
import Pagination from './Pagination/Pagination';

import type { RaceData, Biography, ClassData, PageData } from './types';

import warriorImg from '../../assets/classWarriorImg.png';
import plutImg from '../../assets/classPlutImg.png';
import magicianImg from '../../assets/classMagicianImg.png';
import classInventoryImg from '../../assets/classInventoryImg.png';

const INITIAL_CLASSES: ClassData[] = [
  {
    id: 1,
    name: 'Воин',
    img: warriorImg,
    features: 'Описание воина',
    inventory: [
      { name: 'item1', link: '/shop/item1', img: classInventoryImg },
      { name: 'item2', link: '/shop/item2', img: classInventoryImg },
      { name: 'item3', link: '/shop/item3', img: classInventoryImg },
      { name: 'item4', link: '/shop/item4', img: classInventoryImg },
    ],
    skills: [
      { name: 'skill1', link: '/shop/skill1', img: classInventoryImg },
      { name: 'skill2', link: '/shop/skill2', img: classInventoryImg },
      { name: 'skill3', link: '/shop/skill3', img: classInventoryImg },
    ],
  },
  {
    id: 2,
    name: 'Плут',
    img: plutImg,
    features: 'Описание плута',
    inventory: [
      { name: 'item1', link: '/shop/item1', img: classInventoryImg },
      { name: 'item2', link: '/shop/item2', img: classInventoryImg },
      { name: 'item3', link: '/shop/item3', img: classInventoryImg },
      { name: 'item4', link: '/shop/item4', img: classInventoryImg },
    ],
    skills: [
      { name: 'skill1', link: '/shop/skill1', img: classInventoryImg },
      { name: 'skill2', link: '/shop/skill2', img: classInventoryImg },
      { name: 'skill3', link: '/shop/skill3', img: classInventoryImg },
    ],
  },
  {
    id: 3,
    name: 'Маг',
    img: magicianImg,
    features: 'Описание мага',
    inventory: [
      { name: 'item1', link: '/shop/item1', img: classInventoryImg },
      { name: 'item2', link: '/shop/item2', img: classInventoryImg },
      { name: 'item3', link: '/shop/item3', img: classInventoryImg },
      { name: 'item4', link: '/shop/item4', img: classInventoryImg },
    ],
    skills: [
      { name: 'skill1', link: '/shop/skill1', img: classInventoryImg },
      { name: 'skill2', link: '/shop/skill2', img: classInventoryImg },
      { name: 'skill3', link: '/shop/skill3', img: classInventoryImg },
    ],
  },
];

const PAGE_TITLES = [
  'Выбор расы',
  'Выбор класса',
  'Ввод биографии',
  'Ваш персонаж',
];

export default function CreateCharacterPage() {
  const navigateTo = useNavigateTo();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedRaceId, setSelectedRaceId] = useState<number>(0);
  const [selectedSubraceId, setSelectedSubraceId] = useState<number | null>(null);
  const [selectedClassId, setSelectedClassId] = useState(1);
  const [biography, setBiography] = useState<Biography>({
    biography: '',
    personality: '',
    appearance: '',
    name: '',
    age: '',
    height: '',
    weight: '',
    background: '',
    sex: '',
  });

  const [races, setRaces] = useState<RaceData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useRequireAuth();

  // When selected race changes, auto-select first subrace
  useEffect(() => {
    const race = races.find((r) => r.id_race === selectedRaceId);
    if (race && race.subraces.length > 0) {
      setSelectedSubraceId(race.subraces[0].id_subrace);
    } else {
      setSelectedSubraceId(null);
    }
  }, [selectedRaceId, races]);

  // Fetch races from API
  useEffect(() => {
    axios
      .get<RaceData[]>('/characters/races')
      .then((response) => {
        const fetchedRaces = response.data;
        setRaces(fetchedRaces);

        if (fetchedRaces.length > 0) {
          setSelectedRaceId(fetchedRaces[0].id_race);
          if (fetchedRaces[0].subraces.length > 0) {
            setSelectedSubraceId(fetchedRaces[0].subraces[0].id_subrace);
          }
        }

        setLoading(false);
      })
      .catch(() => {
        setError('Не удалось загрузить расы');
        toast.error('Не удалось загрузить данные рас. Попробуйте обновить страницу.');
        setLoading(false);
      });
  }, []);

  const handleFormValuesChange = (formValues: Biography) => {
    setBiography(formValues);
  };

  const pages: PageData[] = [
    { pageId: 0, pageTitle: PAGE_TITLES[0] },
    { pageId: 1, pageTitle: PAGE_TITLES[1] },
    { pageId: 2, pageTitle: PAGE_TITLES[2] },
    { pageId: 3, pageTitle: PAGE_TITLES[3] },
  ];

  const renderComponentById = (id: number) => {
    if (loading) {
      return (
        <div className="flex items-center justify-center py-20">
          <div className="w-10 h-10 border-4 border-white/30 border-t-white rounded-full animate-spin" />
        </div>
      );
    }
    if (error) {
      return (
        <p className="text-site-red text-center py-10">{error}</p>
      );
    }

    switch (id) {
      case 0:
        return (
          <RacePage
            races={races}
            selectedRaceId={selectedRaceId}
            selectedSubraceId={selectedSubraceId}
            onSelectRaceId={(raceId: number) => setSelectedRaceId(raceId)}
            onSelectSubraceId={(subraceId: number) => setSelectedSubraceId(subraceId)}
          />
        );
      case 1:
        return (
          <ClassPage
            classes={INITIAL_CLASSES}
            selectedClassId={selectedClassId}
            onSelectClass={(classId: number) => setSelectedClassId(classId)}
          />
        );
      case 2:
        return (
          <BiographyPage
            onFormValuesChange={handleFormValuesChange}
            enteredFormValues={biography}
          />
        );
      case 3: {
        const selectedRace = races.find(
          (r) => r.id_race === selectedRaceId,
        );
        const selectedSubrace = selectedRace?.subraces?.find(
          (s) => s.id_subrace === selectedSubraceId,
        );
        const selectedClass = INITIAL_CLASSES.find(
          (cls) => cls.id === selectedClassId,
        );

        return (
          <SubmitPage
            biography={biography}
            selectedRace={selectedRace?.name || ''}
            selectedRaceId={selectedRaceId}
            selectedSubrace={selectedSubrace?.name || ''}
            selectedSubraceId={selectedSubraceId}
            selectedClass={selectedClass?.name || ''}
            selectedClassId={selectedClassId}
          />
        );
      }

      default:
        return null;
    }
  };

  return (
    <div className="rounded-card py-[37px] pb-[70px] bg-site-bg flex flex-col items-center">
      {/* Header section */}
      <div className="relative flex flex-col items-center justify-center gap-[15px] pb-[44px] mb-[15px] after:content-[''] after:absolute after:bottom-0 after:left-1/2 after:h-px after:bg-gradient-to-r after:from-transparent after:via-[#999] after:to-transparent after:z-[1] after:-translate-x-1/2 after:w-[70%]">
        <h1 className="gold-text text-2xl sm:text-[32px] font-bold uppercase text-center">
          Создание персонажа
        </h1>
        <p className="w-[90%] sm:w-[45%] text-center text-base font-normal text-white">
          Здесь вы можете создать своего героя, которым начнете исследование
          Халдеи. Прежде чем отправить заявку на проверку, рекомендуем
          ознакомиться с{' '}
          <a
            onClick={() => navigateTo('/rules')}
            className="underline cursor-pointer hover:text-site-blue transition-colors"
          >
            правилами
          </a>
          .
        </p>
      </div>

      {/* Step title */}
      <h2 className="gold-text text-xl sm:text-[28px] font-semibold text-center mb-10">
        {pages[currentIndex].pageTitle}
      </h2>

      {/* Page content */}
      <div className="flex flex-col items-center w-full flex-1 justify-between mb-10">
        {renderComponentById(pages[currentIndex].pageId)}
      </div>

      {/* Pagination */}
      <Pagination
        pages={pages}
        currentIndex={currentIndex}
        onIndexChange={setCurrentIndex}
      />
    </div>
  );
}
