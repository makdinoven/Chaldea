import Header from '../CommonComponents/Header/Header';

import styles from './CreateCharacterPage.module.css';

export default function CreateCharacterPage({}) {
  return (
    <>
      <Header showMenu={true} />

      <div className={styles.container}>
        <div className={styles.top_container}>
          <h1 className={styles.title}>Создание персонажа</h1>
          <p className={styles.description}>
            Здесь вы можете создать своего героя, которым начнете исследование
            Халдеи. Прежде чем отправить заявку на проверку, рекомендуем
            ознакомиться с правилами.
          </p>
        </div>
      </div>
    </>
  );
}
