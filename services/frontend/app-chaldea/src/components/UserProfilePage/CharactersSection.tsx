import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { User } from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  loadUserCharacters,
  selectUserCharacters,
  selectCharactersLoading,
} from '../../redux/slices/userProfileSlice';

interface CharactersSectionProps {
  profileUserId: number;
}

const CharactersSection = ({ profileUserId }: CharactersSectionProps) => {
  const dispatch = useAppDispatch();
  const characters = useAppSelector(selectUserCharacters);
  const loading = useAppSelector(selectCharactersLoading);

  useEffect(() => {
    dispatch(loadUserCharacters(profileUserId));
  }, [dispatch, profileUserId]);

  if (loading) {
    return (
      <div className="gray-bg p-5">
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-2 border-white/20 border-t-white rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  if (characters.length === 0) {
    return (
      <div className="gray-bg p-5">
        <div className="flex items-center justify-center py-12">
          <p className="text-white/40 text-sm">У пользователя нет персонажей</p>
        </div>
      </div>
    );
  }

  return (
    <div className="gray-bg p-5">
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-6">
        {characters.map((char) => (
          <Link
            key={char.id}
            to="/profile"
            className="flex flex-col items-center gap-2 group"
          >
            <div className="w-[80px] h-[80px] rounded-full gold-outline relative overflow-hidden bg-black/30 flex items-center justify-center group-hover:shadow-hover transition-shadow">
              {char.avatar ? (
                <img
                  src={char.avatar}
                  alt={char.name}
                  className="w-full h-full object-cover"
                />
              ) : (
                <User size={32} className="text-white/20" />
              )}
            </div>
            <div className="flex flex-col items-center gap-0.5 text-center">
              <span className="text-white text-sm font-medium group-hover:text-site-blue transition-colors">
                {char.name}
              </span>
              <span className="text-white/40 text-xs">
                {char.rp_posts_count} {char.rp_posts_count === 1 ? 'пост' : 'постов'}
              </span>
              <span className="text-white/30 text-xs">
                {char.last_rp_post_date
                  ? new Date(char.last_rp_post_date).toLocaleDateString('ru-RU')
                  : 'Нет данных'}
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
};

export default CharactersSection;
