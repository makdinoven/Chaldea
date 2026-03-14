import toast from 'react-hot-toast';
import UserAvatar from '../../CommonComponents/UserAvatar/UserAvatar';
import CharacterInfo from '../../CreateCharacterPage/SubmitPage/CharacterInfo/CharacterInfo';
import axios from 'axios';
import RequestButton from './RequestButton/RequestButton';
import CharacterInfoSmall from '../../CreateCharacterPage/SubmitPage/CharacterInfoSmall/CharacterInfoSmall.jsx';

interface RequestData {
  request_id: number;
  name: string;
  avatar: string | null;
  biography: string;
  background: string;
  appearance: string;
  race_name: string;
  subrace_name: string;
  class_name: string;
  age: number | null;
  height: string | null;
  sex: string | null;
}

interface RequestProps {
  data: RequestData;
}

const Request = ({ data }: RequestProps) => {
  const biographyItems = [
    { title: 'Биография', text: data.biography },
    { title: 'Личность', text: data.background },
    { title: 'Внешность', text: data.appearance },
  ];

  const buttons = [
    { type: 'confirm', text: 'Одобрить' },
    { type: 'cancel', text: 'Отклонить' },
  ];

  const characterItemsSmall = [
    { text: `${data.race_name} - ${data.subrace_name}` },
    { text: data.class_name },
    { text: data.age ? `Возраст : ${data.age}` : null },
    { text: data.height ? `Рост : ${data.height}` : null },
    { text: data.sex ? `Пол : ${data.sex}` : null },
    { text: data.background || null },
  ];

  const handleButtonClick = (type: string) => {
    if (type === 'confirm') {
      axios
        .post(`/characters/requests/${data.request_id}/approve`)
        .then((res) => {
          if (res.status === 200) {
            toast.success('Заявка одобрена');
          }
        })
        .catch(() => {
          toast.error('Не удалось одобрить заявку');
        });
    }
    if (type === 'cancel') {
      axios
        .post(`/characters/requests/${data.request_id}/reject`)
        .then((res) => {
          if (res.status === 200) {
            toast.success('Заявка отклонена');
          }
        })
        .catch(() => {
          toast.error('Не удалось отклонить заявку');
        });
    }
  };

  return (
    <div className="w-full bg-[rgba(24,30,32,0.7)] rounded-[15px] flex gap-5">
      <div className="py-[21px] pl-9">
        <UserAvatar img={data.avatar} name={data.name} />
        <div className="mt-2">
          {characterItemsSmall.map(
            (item, index) =>
              item.text && (
                <CharacterInfoSmall
                  key={index}
                  title={undefined}
                  text={item.text}
                />
              )
          )}
        </div>
      </div>
      <div className="py-5 flex flex-col gap-10 w-full">
        {biographyItems.map((item, index) => (
          <CharacterInfo key={index} title={item.title} text={item.text} />
        ))}
      </div>
      <div className="relative pt-2.5 w-[208px] flex flex-col gap-2.5 before:content-[''] before:absolute before:top-0 before:left-0 before:h-full before:w-px before:bg-gradient-to-b before:from-transparent before:via-[#999] before:to-transparent before:z-[1]">
        {buttons.map((button) => (
          <RequestButton
            key={button.type}
            text={button.text}
            onClick={() => handleButtonClick(button.type)}
          />
        ))}
      </div>
    </div>
  );
};

export default Request;
