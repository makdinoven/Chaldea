import {useState, useEffect} from 'react';
import useNavigateTo from '../../hooks/useNavigateTo';
import {useRequireAuth} from '../../hooks/useRequireAuth';
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
    const [selectedSubraceId, setSelectedSubraceId] = useState(0);
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
                        {name: 'item1', link: '/shop/item1', img: classInventoryImg},
                        {name: 'item2', link: '/shop/item2', img: classInventoryImg},
                        {name: 'item3', link: '/shop/item3', img: classInventoryImg},
                        {name: 'item4', link: '/shop/item4', img: classInventoryImg},
                    ],
                    skills: [
                        {name: 'skill1', link: '/shop/skill1', img: classInventoryImg},
                        {name: 'skill2', link: '/shop/skill2', img: classInventoryImg},
                        {name: 'skill3', link: '/shop/skill3', img: classInventoryImg},
                    ],
                },
                {
                    id: 2,
                    name: 'Плут',
                    img: plutImg,
                    features: 'Описание плута',
                    inventory: [
                        {name: 'item1', link: '/shop/item1', img: classInventoryImg},
                        {name: 'item2', link: '/shop/item2', img: classInventoryImg},
                        {name: 'item3', link: '/shop/item3', img: classInventoryImg},
                        {name: 'item4', link: '/shop/item4', img: classInventoryImg},
                    ],
                    skills: [
                        {name: 'skill1', link: '/shop/skill1', img: classInventoryImg},
                        {name: 'skill2', link: '/shop/skill2', img: classInventoryImg},
                        {name: 'skill3', link: '/shop/skill3', img: classInventoryImg},
                    ],
                },
                {
                    id: 3,
                    name: 'Маг',
                    img: magicianImg,
                    features: 'Описание мага',
                    inventory: [
                        {name: 'item1', link: '/shop/item1', img: classInventoryImg},
                        {name: 'item2', link: '/shop/item2', img: classInventoryImg},
                        {name: 'item3', link: '/shop/item3', img: classInventoryImg},
                        {name: 'item4', link: '/shop/item4', img: classInventoryImg},
                    ],
                    skills: [
                        {name: 'skill1', link: '/shop/skill1', img: classInventoryImg},
                        {name: 'skill2', link: '/shop/skill2', img: classInventoryImg},
                        {name: 'skill3', link: '/shop/skill3', img: classInventoryImg},
                    ],
                },
            ],
        },
        {pageId: 2, pageTitle: 'Ввод биографии'},
        {pageId: 3, pageTitle: 'Ваш персонаж'},
    ]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const race = data[0].races.find((r) => r.id_race === selectedRaceId);
        if (race && race.subraces.length > 0) {
            setSelectedSubraceId(race.subraces[0].id_subrace);
        } else {
            setSelectedSubraceId(null);
        }
    }, [selectedRaceId]);

    useEffect(() => {
        axios
            .get('http://4452515-co41851.twc1.net:8005/characters/metadata', {
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

                if (fetchedRaces.length > 0) {
                    setSelectedRaceId(fetchedRaces[0].id_race);

                    if (fetchedRaces[0].subraces.length > 0) {
                        setSelectedSubraceId(fetchedRaces[0].subraces[0].id_subrace);
                    } else {
                        setSelectedSubraceId(null);
                    }
                }

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
                const selectedRace = data[0].races.find((r) => r.id_race === selectedRaceId);
                const selectedSubrace = selectedRace?.subraces?.find((s) => s.id_subrace === selectedSubraceId);
                const selectedClass = data[1].classes.find((cls) => cls.id === selectedClassId);

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
