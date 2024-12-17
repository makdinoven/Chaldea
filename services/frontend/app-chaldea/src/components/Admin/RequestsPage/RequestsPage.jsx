import { useEffect, useState } from 'react';
import Header from '../../CommonComponents/Header/Header';
import Request from '../Request/Request';

import styles from './RequestsPage.module.css';
import userAvatar from '../../../assets/userAvatarReq.png';
import axios from 'axios';

export default function RequestsPage() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios
      .get('/characters/moderation-requests', data)
      .then((response) => {
        const dataArray = Object.values(response.data);
        setData(dataArray);
        setLoading(false);
      })
      .catch((error) => {
        console.error('Ошибка', error);
      });
  }, []);

  return loading ? (
    <span>loading</span>
  ) : (
    <>
      <Header showMenu={true} />
      <h1 className={styles.title}>Заявки на персонажей</h1>
      <div className={styles.requests_container}>
        {data.map((item, index) => (
          <Request key={index} data={item} />
        ))}
      </div>
    </>
  );
}
