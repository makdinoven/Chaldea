import Button, { type ButtonData } from './Button/Button';
import Slider, { type SliderPage } from './Slider/Slider';
import Stats from './Stats/Stats';
import LatestRoleplayPosts from './LatestRoleplayPosts/LatestRoleplayPosts';
import SectionTitle from './SectionTitle';

import button1img from '../../assets/homepagebutton1.png';
import button2img from '../../assets/homepagebutton2.png';
import button3img from '../../assets/homepagebutton3.png';
import smallbuttonimg1 from '../../assets/smallhomebutton1.png';
import smallbuttonimg2 from '../../assets/smallhomebutton2.png';
import smallbuttonimg3 from '../../assets/smallhomebutton3.png';
import smallbuttonimg4 from '../../assets/smallhomebutton4.png';
import sliderImg1 from '../../assets/sliderimg1.png';

export default function HomePage() {
  const buttonsData: ButtonData[] = [
    {
      id: 1,
      titleName: 'Игровой мир',
      titleLink: '/world',
      img: button1img,
      links: [
        { name: 'Персонажи', link: '/characters' },
        { name: 'Навыки', link: '/skill-tree' },
        { name: 'Аукцион', link: '/auction' },
      ],
      type: 'large',
    },
    {
      id: 2,
      titleName: 'Руководство',
      titleLink: '/guide',
      img: button2img,
      links: [
        { name: 'Обучение', link: '/learning' },
        { name: 'Консультант', link: '/consultant' },
        { name: 'Архив', link: '/archive' },
      ],
      type: 'large',
    },
    {
      id: 3,
      titleName: 'Магазин',
      titleLink: '/shop',
      img: button3img,
      links: [
        { name: 'Рулетка', link: '/roulette' },
        { name: 'События', link: '/events' },
        { name: 'Валюта', link: '/currency' },
      ],
      type: 'large',
    },
    {
      id: 4,
      titleLink: '/offers',
      titleName: 'Предложения',
      img: smallbuttonimg1,
      type: 'small',
    },
    {
      id: 5,
      titleLink: '/administration',
      titleName: 'Администрация',
      img: smallbuttonimg2,
      type: 'small',
    },
    {
      id: 6,
      titleLink: '/bestiary',
      titleName: 'Бестиарий',
      img: smallbuttonimg3,
      type: 'small',
    },
    {
      id: 7,
      titleLink: '/findaplayer',
      titleName: 'Поиск игрока',
      img: smallbuttonimg4,
      type: 'small',
    },
  ];

  const sliderData: SliderPage[] = [
    {
      index: 1,
      title: 'Мы открываемся!',
      description: 'Все что нужно знать о запуске проекта',
      link: '/sliderlink1',
      img: sliderImg1,
      tag: 'Технобук',
    },
    {
      index: 2,
      title: 'Мы открываемся!2',
      description: 'Все что нужно знать о запуске проекта2',
      link: '/sliderlink2',
      img: sliderImg1,
      tag: 'Технобук',
    },
    {
      index: 3,
      title: 'Мы открываемся!3',
      description: 'Все что нужно знать о запуске проекта3',
      link: '/sliderlink3',
      img: sliderImg1,
      tag: 'Технобук',
    },
    {
      index: 4,
      title: 'Мы открываемся!4',
      description: 'Все что нужно знать о запуске проекта',
      link: '/sliderlink4',
      img: sliderImg1,
      tag: 'Технобук',
    },
  ];

  const largeButtons = buttonsData.filter((button) => button.type === 'large');
  const smallButtons = buttonsData.filter((button) => button.type === 'small');

  return (
    <>
      {/*
        Top region per the redesign reference: two-column grid (~38% / 62%).
        Left — "Куда отправимся": three large navigation cards stretched to
        match the right column height. Right — "Главное сейчас": hero slider
        (min-height 440px). Collapses to a single column below md (768px).
      */}
      <main className="grid grid-cols-1 gap-y-[34px] md:grid-cols-[38%_1fr] md:gap-x-11">
        <section className="flex flex-col gap-[18px]">
          <SectionTitle label="Куда отправимся" />
          {largeButtons.map((buttonData) => (
            <div key={buttonData.id} className="min-h-[122px] flex-1">
              <Button data={buttonData} />
            </div>
          ))}
        </section>

        <section className="flex min-w-0 flex-col gap-[18px]">
          <SectionTitle label="Главное сейчас" />
          <div className="min-h-[440px] flex-1">
            <Slider pages={sliderData} />
          </div>
        </section>
      </main>

      {/* Quick links: full-width row, 4 -> 2 -> 1 columns (as in the mock) */}
      <section className="mt-8">
        <div className="grid grid-cols-1 gap-[18px] min-[420px]:grid-cols-2 md:grid-cols-4">
          {smallButtons.map((buttonData) => (
            <div key={buttonData.id} className="h-[100px]">
              <Button data={buttonData} />
            </div>
          ))}
        </div>
      </section>

      {/* Live feed: full-width section with the "Онлайн" pulse indicator */}
      <section className="mt-[52px]">
        <SectionTitle label="Живая лента">
          <span className="flex items-center gap-[7px] text-[11px] tracking-[0.08em] text-white/50">
            <span className="h-[7px] w-[7px] rounded-full bg-stat-energy animate-pulse" />
            Онлайн
          </span>
        </SectionTitle>
        <div className="mt-[18px]">
          <LatestRoleplayPosts />
        </div>
      </section>

      {/* Hall of Fame: full-width section wrapper; card internals owned by Stats */}
      <section className="mt-[56px]">
        <SectionTitle label="Зал славы" />
        <div className="mt-[18px]">
          <Stats />
        </div>
      </section>
    </>
  );
}
