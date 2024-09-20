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

  const paramsData = [
    { name: 'Выносливость', value: raceData.raceParameters.stamina },
    { name: 'Здоровье', value: raceData.raceParameters.hp },
    { name: 'Энергия', value: raceData.raceParameters.energy },
    { name: 'Мана', value: raceData.raceParameters.mana },
    { name: 'Живучесть', value: raceData.raceParameters.survivability },
    { name: 'Интеллект', value: raceData.raceParameters.iq },
    { name: 'Ловкость', value: raceData.raceParameters.agility },
    { name: 'Сила', value: raceData.raceParameters.strength },
    { name: 'Харизма', value: raceData.raceParameters.charisma },
    { name: 'Удача', value: raceData.raceParameters.luck },
  ];

  function sliceParams(startIndex, endIndex) {
    return (
      <div className={styles.params_inner}>
        {paramsData.slice(startIndex, endIndex).map((param) => (
          <span key={param.name} className={styles.param}>
            {param.name}: {param.value}
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className={styles.desc_container}>
      <div className={styles.desc_col}>
        <h4 className={styles.desc_title}>{raceData.raceName}</h4>
        <p className={styles.race_info}>{raceData.raceDesc}</p>
      </div>
      <div className={styles.desc_col}>
        <div className={styles.subraces}>
          {raceData.subraces.map((subrace, index) => (
            <SubraceButton
              key={subrace.subraceId}
              text={subrace.subraceName}
              index={index}
              currentIndex={currentIndex}
              setCurrentIndex={setCurrentIndex}
            />
          ))}
        </div>
        <p className={styles.race_info}>
          {raceData.subraces[currentIndex]?.subraceDesc}
        </p>
      </div>
      <div className={styles.desc_col}>
        <h4 className={`${styles.desc_title} ${styles.desc_title_params}`}>
          {raceData.raceParametersTitle}
          <a
            className={styles.question_mark}
            onClick={() => navigateTo('/rules')}
          ></a>
        </h4>
        <div className={styles.params_container}>
          {sliceParams(0, 4)}
          {sliceParams(4, 8)}
        </div>
        {sliceParams(8, paramsData.length)}
      </div>
    </div>
  );
}
