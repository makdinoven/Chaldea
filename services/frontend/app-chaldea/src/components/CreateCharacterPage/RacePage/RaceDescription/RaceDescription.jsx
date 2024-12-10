import { useState, useEffect } from 'react';
import useNavigateTo from '../../../../hooks/useNavigateTo';
import SubraceButton from './SubraceButton/SubraceButton';
import styles from './RaceDescription.module.css';

export default function RaceDescription({
  raceData,
  onSubraceChange,
  selectedSubraceId,
}) {
  const [currentIndex, setCurrentIndex] = useState(selectedSubraceId);
  const navigateTo = useNavigateTo();

  // console.log(raceData.subraces);

  // if (raceData === undefined) {
  //   console.log('raceData undefined');
  //   return null;
  // }

  // useEffect(() => {
  //   console.log('SubraceId changed');
  // }, [currentIndex]);

  useEffect(() => {
    setCurrentIndex(selectedSubraceId);
  }, [selectedSubraceId]);

  useEffect(() => {
    onSubraceChange(currentIndex);
  }, [currentIndex, raceData]);

  // function sliceParams(startIndex, endIndex) {
  //   return (
  //     <div className={styles.params_inner}>
  //       {raceData.subraces[selectedSubraceId].attributes
  //         .slice(startIndex, endIndex)
  //         .map((param) => (
  //           <span key={param.name} className={styles.param}>
  //             {param.name}: {param.value}
  //           </span>
  //         ))}
  //     </div>
  //   );
  // }

  const attributeTranslations = {
    agility: 'Ловкость',
    charisma: 'Харизма',
    endurance: 'Выносливость',
    energy: 'Энергия',
    health: 'Здоровье',
    intelligence: 'Интеллект',
    luck: 'Удача',
    mana: 'Мана',
    stamina: 'Сила',
    strength: 'Сила',
  };

  return (
    <div className={styles.desc_container}>
      <div className={styles.desc_col}>
        <h4 className={styles.desc_title}>{raceData.name}</h4>
        <p className={styles.race_info}>{raceData.description}</p>
      </div>
      <div className={styles.desc_col}>
        <div className={styles.subraces}>
          {raceData.subraces.map((subrace, index) => (
            <SubraceButton
              key={subrace.id_subrace}
              text={subrace.name}
              index={index}
              currentIndex={currentIndex}
              setCurrentIndex={setCurrentIndex}
            />
          ))}
        </div>
        <p className={styles.race_info}>
          {raceData.subraces[currentIndex]?.description}
        </p>
      </div>
      <div className={styles.desc_col}>
        <h4 className={`${styles.desc_title} ${styles.desc_title_params}`}>
          Характеристики
          <a
            className={styles.question_mark}
            onClick={() => navigateTo('/rules')}
          ></a>
        </h4>
        <div className={styles.params_container}>
          {Object.entries(raceData.subraces[selectedSubraceId].attributes).map(
            ([key, value]) => {
              return (
                <span key={key} className={styles.param}>
                  {attributeTranslations[key] || key}: {value}
                </span>
              );
            }
          )}
        </div>
      </div>
    </div>
  );
}
