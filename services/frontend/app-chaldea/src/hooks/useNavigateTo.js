//это хук для того чтобы роуты делать, кидается на обработчик клика , принимает ссылку
import { useNavigate } from 'react-router-dom';

export default function useNavigateTo() {
  const navigate = useNavigate();

  return (link) => {
    if (link === '/') {
      localStorage.removeItem('accessToken');
    }
    if (link) {
      navigate(link);
    } else {
      console.log('No link provided');
    }
  };
}
