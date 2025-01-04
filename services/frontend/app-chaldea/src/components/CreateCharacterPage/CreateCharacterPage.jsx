import { useState, useEffect } from 'react';
import useNavigateTo from '../../hooks/useNavigateTo';
import { useRequireAuth } from '../../hooks/useRequireAuth';
import axios from 'axios';

import RacePage from './RacePage/RacePage';
import ClassPage from './ClassPage/ClassPage';
import BiographyPage from './BiographyPage/BiographyPage';
import SubmitPage from './SubmitPage/SubmitPage';

import Pagination from './Pagination/Pagination';

import styles from './CreateCharacterPage.module.scss';

import elfImg from '../../assets/elfImage.png';
import starikImg from '../../assets/starikImage.png';
import warriorImg from '../../assets/classWarriorImg.png';
import plutImg from '../../assets/classPlutImg.png';
import magicianImg from '../../assets/classMagicianImg.png';
import classInventoryImg from '../../assets/classInventoryImg.png';
import {useUser} from "../../hooks/UserContext.jsx";

export default function CreateCharacterPage({}) {
  const navigateTo = useNavigateTo();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedRaceId, setSelectedRaceId] = useState(1);
  const [selectedSubraceId, setSelectedSubraceId] = useState(1);
  const [selectedClassId, setSelectedClassId] = useState(1);
  const [biography, setBiography] = useState({
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

  const [data, setData] = useState([
    {
      pageId: 0,
      pageTitle: 'Выбор расы',
      races: [],
    },
    {
      pageId: 1,
      pageTitle: 'Выбор класса',
      classes: [
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
      ],
    },
    { pageId: 2, pageTitle: 'Ввод биографии' },
    { pageId: 3, pageTitle: 'Ваш персонаж' },
  ]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // const data = [
  //   {
  //     pageId: 0,
  //     pageTitle: 'Выбор расы',
  //     pageData: {
  //       // races: [
  //       //   {
  //       //     raceId: 0,
  //       //     raceName: 'Эльф',
  //       //     raceImg: elfImg,
  //       //     raceParametersTitle: 'Характеристики',
  //       //     raceParameters: {
  //       //       stamina: 125,
  //       //       hp: 150,
  //       //       energy: 100,
  //       //       mana: 75,
  //       //       survivability: 0,
  //       //       iq: 20,
  //       //       agility: 30,
  //       //       strength: 0,
  //       //       charisma: 20,
  //       //       luck: 10,
  //       //     },
  //       //     raceDesc:
  //       //       'Одна из немногочисленных гуманоидных рас, которые отличаются относительно высоким ростом (до 200 сантиметров) и долгим сроком жизни (до 200 лет). Проживают на материке Халдея, и делятся на три народа. Отличаются немногочисленностью и отстранённостью. Имеют три национальных государства, в которых обычно проживают: Малахия, Альбина и Гноста.',
  //       //     subraces: [
  //       //       {
  //       //         subraceId: 0,
  //       //         subraceName: 'Лесной',
  //       //         subraceDesc:
  //       //           'Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
  //       //       },
  //       //       {
  //       //         subraceId: 1,
  //       //         subraceName: 'Темный',
  //       //         subraceDesc:
  //       //           'ТЕМНЫЙ Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
  //       //       },
  //       //       {
  //       //         subraceId: 2,
  //       //         subraceName: 'Малах',
  //       //         subraceDesc:
  //       //           'МАЛАХ Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
  //       //       },
  //       //     ],
  //       //   },
  //       //   {
  //       //     raceId: 1,
  //       //     raceName: 'Старик',
  //       //     raceImg: starikImg,
  //       //     raceParametersTitle: 'Характеристики',
  //       //     raceParameters: {
  //       //       stamina: 135,
  //       //       hp: 200,
  //       //       energy: 100,
  //       //       mana: 75,
  //       //       survivability: 0,
  //       //       iq: 50,
  //       //       agility: 30,
  //       //       strength: 100,
  //       //       charisma: 30,
  //       //       luck: 0,
  //       //     },
  //       //     raceDesc:
  //       //       'Одна из немногочисленных гуманоидных рас, которые отличаются относительно высоким ростом (до 200 сантиметров) и долгим сроком жизни (до 200 лет). Проживают на материке Халдея, и делятся на три народа. Отличаются немногочисленностью и отстранённостью. Имеют три национальных государства, в которых обычно проживают: Малахия, Альбина и Гноста.',
  //       //     subraces: [
  //       //       {
  //       //         subraceId: 0,
  //       //         subraceName: 'Старый',
  //       //         subraceDesc:
  //       //           'Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
  //       //       },
  //       //       {
  //       //         subraceId: 1,
  //       //         subraceName: 'Средний',
  //       //         subraceDesc:
  //       //           'ТЕМНЫЙ Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
  //       //       },
  //       //       {
  //       //         subraceId: 2,
  //       //         subraceName: 'Янг',
  //       //         subraceDesc:
  //       //           'МАЛАХ Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
  //       //       },
  //       //     ],
  //       //   },
  //       //   {
  //       //     raceId: 2,
  //       //     raceName: 'Эльф2',
  //       //     raceImg: elfImg,
  //       //     raceParametersTitle: 'Характеристики',
  //       //     raceParameters: {
  //       //       stamina: 125,
  //       //       hp: 150,
  //       //       energy: 100,
  //       //       mana: 75,
  //       //       survivability: 0,
  //       //       iq: 20,
  //       //       agility: 30,
  //       //       strength: 0,
  //       //       charisma: 20,
  //       //       luck: 10,
  //       //     },
  //       //     raceDesc:
  //       //       'Одна из немногочисленных гуманоидных рас, которые отличаются относительно высоким ростом (до 200 сантиметров) и долгим сроком жизни (до 200 лет). Проживают на материке Халдея, и делятся на три народа. Отличаются немногочисленностью и отстранённостью. Имеют три национальных государства, в которых обычно проживают: Малахия, Альбина и Гноста.',
  //       //     subraces: [
  //       //       {
  //       //         subraceId: 0,
  //       //         subraceName: 'Лесной',
  //       //         subraceDesc:
  //       //           'Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
  //       //       },
  //       //       {
  //       //         subraceId: 1,
  //       //         subraceName: 'Темный',
  //       //         subraceDesc:
  //       //           'ТЕМНЫЙ Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
  //       //       },
  //       //       {
  //       //         subraceId: 2,
  //       //         subraceName: 'Малах',
  //       //         subraceDesc:
  //       //           'МАЛАХ Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
  //       //       },
  //       //     ],
  //       //   },
  //       //   {
  //       //     raceId: 3,
  //       //     raceName: 'Старик2',
  //       //     raceImg: starikImg,
  //       //     raceParametersTitle: 'Характеристики',
  //       //     raceParameters: {
  //       //       stamina: 125,
  //       //       hp: 150,
  //       //       energy: 100,
  //       //       mana: 75,
  //       //       survivability: 0,
  //       //       iq: 20,
  //       //       agility: 30,
  //       //       strength: 0,
  //       //       charisma: 20,
  //       //       luck: 10,
  //       //     },
  //       //     raceDesc:
  //       //       'Одна из немногочисленных гуманоидных рас, которые отличаются относительно высоким ростом (до 200 сантиметров) и долгим сроком жизни (до 200 лет). Проживают на материке Халдея, и делятся на три народа. Отличаются немногочисленностью и отстранённостью. Имеют три национальных государства, в которых обычно проживают: Малахия, Альбина и Гноста.',
  //       //     subraces: [
  //       //       {
  //       //         subraceId: 0,
  //       //         subraceName: 'Лесной',
  //       //         subraceDesc:
  //       //           'Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
  //       //       },
  //       //       {
  //       //         subraceId: 1,
  //       //         subraceName: 'Темный',
  //       //         subraceDesc:
  //       //           'ТЕМНЫЙ Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
  //       //       },
  //       //       {
  //       //         subraceId: 2,
  //       //         subraceName: 'Малах',
  //       //         subraceDesc:
  //       //           'МАЛАХ Условное название одной из ортодоксальных групп эльфов, которые сохраняют традиции предков. Происходят в основном из государства Альбина на северо-западе Халдеи, и имеют острые противоречия со своими сородичами тёмными эльфами. Отличаются бледной кожей, высоким ростом и худощавым телосложением. Встречаются и за пределами Альбины – но чаще всего это переселенцы.',
  //       //       },
  //       //     ],
  //       //   },
  //       // ],
  //     },
  //   },
  //   {
  //     pageId: 1,
  //     pageTitle: 'Выбор класса',
  //     classes: [
  //       {
  //         id: 0,
  //         name: 'Воин',
  //         img: warriorImg,
  //         features: 'Описание воина',
  //         inventory: [
  //           { name: 'item1', link: '/shop/item1', img: classInventoryImg },
  //           { name: 'item2', link: '/shop/item2', img: classInventoryImg },
  //           { name: 'item3', link: '/shop/item3', img: classInventoryImg },
  //           { name: 'item4', link: '/shop/item4', img: classInventoryImg },
  //         ],
  //         skills: [
  //           { name: 'skill1', link: '/shop/skill1', img: classInventoryImg },
  //           { name: 'skill2', link: '/shop/skill2', img: classInventoryImg },
  //           { name: 'skill3', link: '/shop/skill3', img: classInventoryImg },
  //         ],
  //       },
  //       {
  //         id: 1,
  //         name: 'Плут',
  //         img: plutImg,
  //         features: 'Описание плута',
  //         inventory: [
  //           { name: 'item1', link: '/shop/item1', img: classInventoryImg },
  //           { name: 'item2', link: '/shop/item2', img: classInventoryImg },
  //           { name: 'item3', link: '/shop/item3', img: classInventoryImg },
  //           { name: 'item4', link: '/shop/item4', img: classInventoryImg },
  //         ],
  //         skills: [
  //           { name: 'skill1', link: '/shop/skill1', img: classInventoryImg },
  //           { name: 'skill2', link: '/shop/skill2', img: classInventoryImg },
  //           { name: 'skill3', link: '/shop/skill3', img: classInventoryImg },
  //         ],
  //       },
  //       {
  //         id: 2,
  //         name: 'Маг',
  //         img: magicianImg,
  //         features: 'Описание мага',
  //         inventory: [
  //           { name: 'item1', link: '/shop/item1', img: classInventoryImg },
  //           { name: 'item2', link: '/shop/item2', img: classInventoryImg },
  //           { name: 'item3', link: '/shop/item3', img: classInventoryImg },
  //           { name: 'item4', link: '/shop/item4', img: classInventoryImg },
  //         ],
  //         skills: [
  //           { name: 'skill1', link: '/shop/skill1', img: classInventoryImg },
  //           { name: 'skill2', link: '/shop/skill2', img: classInventoryImg },
  //           { name: 'skill3', link: '/shop/skill3', img: classInventoryImg },
  //         ],
  //       },
  //     ],
  //   },
  //   { pageId: 2, pageTitle: 'Ввод биографии' },
  //   { pageId: 3, pageTitle: 'Ваш персонаж' },
  // ];

  useEffect(() => {
    axios
      .get('http://localhost:8005/characters/metadata', {
        headers: {
          Accept: 'application/json',
        },
      })

      .then((response) => {
        const fetchedRaces = response.data;
        setData((prevData) =>
          prevData.map((item) => {
            if (item.pageId === 0) {
              return {
                ...item,
                races: fetchedRaces,
              };
            }
            return item;
          })
        );
        setLoading(false);
      })
      .catch((error) => setError(error));
  }, []);

  useRequireAuth();

  const handleFormValuesChange = (formValues) => {
    setBiography(formValues);
  };

  const renderComponentById = (id) => {
    if (loading) return <p>Loading...</p>;
    if (error) return <p>Error: {error}</p>;

    switch (id) {
      case 0:
        return (
          <RacePage
            races={data[id].races}
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
            onFormValuesChange={handleFormValuesChange}
            enteredFormValues={biography}
          />
        );
      case 3:
        return (
          <SubmitPage
            biography={biography}
            selectedRace={data[0].races[selectedRaceId].name}
            selectedRaceId={selectedRaceId}
            selectedSubrace={
              data[0].races[selectedRaceId].subraces[selectedSubraceId].name
            }
            selectedSubraceId={selectedSubraceId}
            selectedClass={data[1].classes[selectedClassId -1].name}
            selectedClassId={selectedClassId}
          />
        );

      default:
        return null;
    }
  };

  return (
    <>
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
