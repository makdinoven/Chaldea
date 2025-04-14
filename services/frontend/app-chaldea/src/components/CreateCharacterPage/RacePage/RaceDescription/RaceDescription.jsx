import useNavigateTo from '../../../../hooks/useNavigateTo';
import SubraceButton from './SubraceButton/SubraceButton';
import styles from './RaceDescription.module.scss';

export default function RaceDescription({
                                            raceData,
                                            onSubraceChange,
                                            selectedSubraceId,
                                        }) {
    const navigateTo = useNavigateTo();

    const selectedSubrace = raceData.subraces.find(
        (subrace) => subrace?.id_subrace === selectedSubraceId
    );

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
                    {raceData.subraces.map((subrace) => (
                        <SubraceButton
                            key={subrace.id_subrace}
                            text={subrace.name}
                            index={subrace.id_subrace}
                            isActive={selectedSubraceId === subrace.id_subrace}
                            setCurrentIndex={onSubraceChange}
                        />
                    ))}
                </div>
                <p className={styles.race_info}>{selectedSubrace?.description}</p>
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
                    {selectedSubrace &&
                        Object.entries(selectedSubrace.attributes || {}).map(
                            ([key, value]) => (
                                <span key={key} className={styles.param}>
                                    {attributeTranslations[key] || key}: {value}
                                </span>
                            )
                        )}
                </div>
            </div>
        </div>
    );
}
