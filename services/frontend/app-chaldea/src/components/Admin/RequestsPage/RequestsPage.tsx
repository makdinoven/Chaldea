import { useEffect, useState } from 'react';
import Request from '../Request/Request';
import axios from 'axios';

interface ModerationRequest {
  request_id: number;
  user_id: number;
  name: string;
  biography: string;
  appearance: string;
  personality: string;
  background: string;
  age: number | null;
  weight: string | null;
  height: string | null;
  sex: string | null;
  id_class: number;
  class_name: string;
  id_race: number;
  race_name: string;
  id_subrace: number;
  subrace_name: string;
  status: string;
  created_at: string;
  avatar: string | null;
  request_type: string;
  character_id: number | null;
}

export default function RequestsPage() {
  const [data, setData] = useState<ModerationRequest[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    axios
      .get('/characters/moderation-requests')
      .then((response) => {
        const dataArray = Object.values(response.data) as ModerationRequest[];
        setData(dataArray);
        setLoading(false);
      })
      .catch(() => {
        setError('Не удалось загрузить заявки. Попробуйте позже.');
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <span className="text-white text-lg">Загрузка...</span>;
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-4 mt-8">
        <p className="text-red-500 text-xl font-semibold">{error}</p>
      </div>
    );
  }

  const handleStatusChange = (requestId: number) => {
    setData((prev) => prev.filter((item) => item.request_id !== requestId));
  };

  const pendingRequests = data.filter((item) => item.status === 'pending');

  return (
    <>
      <h1 className="font-bold text-[32px] text-center text-[color:var(--zoloto)] mb-6">
        Заявки на персонажей
      </h1>
      <div className="flex flex-col gap-20">
        {pendingRequests.length > 0 ? (
          pendingRequests.map((item) => (
            <Request key={item.request_id} data={item} requestType={item.request_type} onStatusChange={handleStatusChange} />
          ))
        ) : (
          <h2 className="font-semibold text-[26px] text-center text-[color:var(--zoloto)]">
            Заявок нет
          </h2>
        )}
      </div>
    </>
  );
}
