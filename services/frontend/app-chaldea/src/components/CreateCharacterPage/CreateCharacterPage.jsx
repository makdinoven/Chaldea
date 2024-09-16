import { useState, useEffect, memo } from 'react';
import useNavigateTo from '../../hooks/useNavigateTo';
import { useRequireAuth } from '../../hooks/useRequireAuth';

import Header from '../CommonComponents/Header/Header';
import RacePage from './RacePage/RacePage';
import ClassPage from './ClassPage/ClassPage';
import BiographyPage from './BiographyPage/BiographyPage';

import Pagination from './Pagination/Pagination';

import styles from './CreateCharacterPage.module.css';

import elfImg from '../../assets/elfImage.png';
import starikImg from '../../assets/starikImage.png';
import warriorImg from '../../assets/classWarriorImg.png';
import plutImg from '../../assets/classPlutImg.png';
import magicianImg from '../../assets/classMagicianImg.png';

export default function CreateCharacterPage({}) {
  const navigateTo = useNavigateTo();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedRaceId, setSelectedRaceId] = useState(0);
  const [selectedSubraceId, setSelectedSubraceId] = useState(0);
  const [selectedClassId, setSelectedClassId] = useState(0);

  useRequireAuth();

  // useEffect(() => {
  //   console.log('CreateCharacterPage rendered');
  // }, []);

  // useEffect(() => {
  //   console.log('Selected Race:', selectedRaceId);
  //   console.log('Selected Subrace:', selectedSubraceId);
  //   console.log('Selected Class:', selectedClassId);
  // }, [selectedRaceId, selectedSubraceId, selectedClassId]);

  const renderComponentById = (id) => {
    switch (id) {
      case 0:
        return (
          <RacePage
            races={data[id].pageData.races}
            selectedRaceId={selectedRaceId}
            selectedSubraceId={selectedSubraceId}
            onSelectRaceId={(id) => {
              setSelectedRaceId(id);
            }}
            onSelectSubraceId={(id) => {
              setSelectedSubraceId(id);
            }}
          />
        );
      case 1:
        return (
          <ClassPage
            classes={data[id].classes}
            selectedClassId={selectedClassId}
            onSelectClass={(className) => setSelectedClassId(className)}
          />
        );
      case 2:
        return (
          <BiographyPage
            selectedRaceId={selectedRaceId}
            selectedSubraceId={selectedSubraceId}
            selectedClassId={selectedClassId}
          />
        );

      default:
        return null;
    }
  };

  const data = [
    {
      pageId: 0,
      pageTitle: 'Выбор расы',
      pageData: {
        races: [
          {
            raceId: 0,
            raceName: 'Эльф',
            raceImg: elfImg,
            raceParametersTitle: 'Характеристики',
            raceParameters: {
              stamina: 125,
              hp: 150,
              energy: 100,
              mana: 75,
              survivability: 0,
              iq: 20,
              agility: 30,
              strength: 0,
              charisma: 20,
              luck: 10,
            },
            raceDesc:
              'Одна из немногочисленных гуманоидных рас, которые отличаются относительно высоким ростом (до 200 сантиметров) и долгим сроком жизни (до 200 лет). Проживают на материке Халдея, и делятся на три народа. Отличаются немногочисленностью и отстранённостью. Имеют три национальных государства, в которых обычно проживают: Малахия, Альбина и Гноста.',
            subraces: [
              {
                subraceId: 0,
                subraceName: 'Лесной',
                subraceDesc:
                  'Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
              },
              {
                subraceId: 1,
                subraceName: 'Темный',
                subraceDesc:
                  'ТЕМНЫЙ Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
              },
              {
                subraceId: 2,
                subraceName: 'Малах',
                subraceDesc:
                  'МАЛАХ Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
              },
            ],
          },
          {
            raceId: 1,
            raceName: 'Старик',
            raceImg: starikImg,
            raceParametersTitle: 'Характеристики',
            raceParameters: {
              stamina: 135,
              hp: 200,
              energy: 100,
              mana: 75,
              survivability: 0,
              iq: 50,
              agility: 30,
              strength: 100,
              charisma: 30,
              luck: 0,
            },
            raceDesc:
              'Одна из немногочисленных гуманоидных рас, которые отличаются относительно высоким ростом (до 200 сантиметров) и долгим сроком жизни (до 200 лет). Проживают на материке Халдея, и делятся на три народа. Отличаются немногочисленностью и отстранённостью. Имеют три национальных государства, в которых обычно проживают: Малахия, Альбина и Гноста.',
            subraces: [
              {
                subraceId: 0,
                subraceName: 'Старый',
                subraceDesc:
                  'Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
              },
              {
                subraceId: 1,
                subraceName: 'Средний',
                subraceDesc:
                  'ТЕМНЫЙ Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
              },
              {
                subraceId: 2,
                subraceName: 'Янг',
                subraceDesc:
                  'МАЛАХ Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
              },
            ],
          },
          {
            raceId: 2,
            raceName: 'Эльф2',
            raceImg: elfImg,
            raceParametersTitle: 'Характеристики',
            raceParameters: {
              stamina: 125,
              hp: 150,
              energy: 100,
              mana: 75,
              survivability: 0,
              iq: 20,
              agility: 30,
              strength: 0,
              charisma: 20,
              luck: 10,
            },
            raceDesc:
              'Одна из немногочисленных гуманоидных рас, которые отличаются относительно высоким ростом (до 200 сантиметров) и долгим сроком жизни (до 200 лет). Проживают на материке Халдея, и делятся на три народа. Отличаются немногочисленностью и отстранённостью. Имеют три национальных государства, в которых обычно проживают: Малахия, Альбина и Гноста.',
            subraces: [
              {
                subraceId: 0,
                subraceName: 'Лесной',
                subraceDesc:
                  'Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
              },
              {
                subraceId: 1,
                subraceName: 'Темный',
                subraceDesc:
                  'ТЕМНЫЙ Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
              },
              {
                subraceId: 2,
                subraceName: 'Малах',
                subraceDesc:
                  'МАЛАХ Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
              },
            ],
          },
          {
            raceId: 3,
            raceName: 'Старик2',
            raceImg: starikImg,
            raceParametersTitle: 'Характеристики',
            raceParameters: {
              stamina: 125,
              hp: 150,
              energy: 100,
              mana: 75,
              survivability: 0,
              iq: 20,
              agility: 30,
              strength: 0,
              charisma: 20,
              luck: 10,
            },
            raceDesc:
              'Одна из немногочисленных гуманоидных рас, которые отличаются относительно высоким ростом (до 200 сантиметров) и долгим сроком жизни (до 200 лет). Проживают на материке Халдея, и делятся на три народа. Отличаются немногочисленностью и отстранённостью. Имеют три национальных государства, в которых обычно проживают: Малахия, Альбина и Гноста.',
            subraces: [
              {
                subraceId: 0,
                subraceName: 'Лесной',
                subraceDesc:
                  'Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
              },
              {
                subraceId: 1,
                subraceName: 'Темный',
                subraceDesc:
                  'ТЕМНЫЙ Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
              },
              {
                subraceId: 2,
                subraceName: 'Малах',
                subraceDesc:
                  'МАЛАХ Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
              },
            ],
          },
        ],
      },
    },
    {
      pageId: 1,
      pageTitle: 'Выбор класса',
      classes: [
        { id: 0, name: 'Воин', img: warriorImg },
        { id: 1, name: 'Плут', img: plutImg },
        { id: 2, name: 'Маг', img: magicianImg },
      ],
    },
    { pageId: 2, pageTitle: 'Ввод биографии', pageData: { images: '' } },
  ];

  return (
    <>
      <Header showMenu={true} />

      <div className={styles.container}>
        <div className={styles.top_container}>
          <h1 className={styles.title}>Создание персонажа</h1>
          <p className={styles.description}>
            Здесь вы можете создать своего героя, которым начнете исследование
            Халдеи. Прежде чем отправить заявку на проверку, рекомендуем
            ознакомиться с <a onClick={() => navigateTo('/rules')}>правилами</a>
            .
          </p>
        </div>

        <h2 className={styles.page_title}>{data[currentIndex].pageTitle}</h2>

        <div className={styles.page}>
          {renderComponentById(data[currentIndex].pageId)}
        </div>
        <Pagination
          pages={data}
          currentIndex={currentIndex}
          onIndexChange={setCurrentIndex}
        />
      </div>
    </>
  );
}
