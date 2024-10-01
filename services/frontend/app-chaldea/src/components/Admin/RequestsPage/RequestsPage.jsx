import Header from '../../CommonComponents/Header/Header';
import Request from '../Request/Request';

import styles from './RequestsPage.module.css';

import userAvatar from '../../../assets/userAvatarReq.png';

export default function RequestsPage() {
  const data = { img: userAvatar, name: 'гарольд ВЕЙЛАНДСОН' };

  return (
    <>
      <Header showMenu={true} />
      <h1 className={styles.title}>Заявки на персонажей</h1>
      <div className={styles.requests_container}>
        <Request data={data} />
        <Request data={data} />
        <Request data={data} />
      </div>
    </>
  );
}
