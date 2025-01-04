import { useEffect, useState } from 'react';
import Request from '../Request/Request';
import styles from './RequestsPage.module.scss';
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
      <h1 className={styles.title}>Заявки на персонажей</h1>
      <div className={styles.requests_container}>
          {data.some(item => item.status === 'pending') ? (
              data.map((item, index) =>
                  item.status === 'pending' && <Request key={index} data={item} />
              )
          ) : (
              <h2>Заявок нет</h2>
          )}
      </div>
    </>
  );
}
