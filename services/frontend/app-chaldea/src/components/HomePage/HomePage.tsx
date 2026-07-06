import Button from "./Button/Button";
import Slider from "./Slider/Slider";
import Stats from "./Stats/Stats";
import LatestRoleplayPosts from "./LatestRoleplayPosts/LatestRoleplayPosts";

import button1img from "../../assets/homepagebutton1.png";
import button2img from "../../assets/homepagebutton2.png";
import button3img from "../../assets/homepagebutton3.png";
import smallbuttonimg1 from "../../assets/smallhomebutton1.png";
import smallbuttonimg2 from "../../assets/smallhomebutton2.png";
import smallbuttonimg3 from "../../assets/smallhomebutton3.png";
import smallbuttonimg4 from "../../assets/smallhomebutton4.png";
import sliderImg1 from "../../assets/sliderimg1.png";

interface ButtonLink {
  name: string;
  link: string;
}

interface ButtonData {
  id: number;
  titleName: string;
  titleLink: string;
  img: string;
  links?: ButtonLink[];
  type: "large" | "small";
}

interface SliderPage {
  index: number;
  title: string;
  description: string;
  link: string;
  img: string;
  tag: string;
}

export default function HomePage() {
  const buttonsData: ButtonData[] = [
    {
      id: 1,
      titleName: "Игровой мир",
      titleLink: "/world",
      img: button1img,
      links: [
        { name: "Персонажи", link: "/characters" },
        { name: "Навыки", link: "/skill-tree" },
        { name: "Аукцион", link: "/auction" },
      ],
      type: "large",
    },
    {
      id: 2,
      titleName: "Руководство",
      titleLink: "/guide",
      img: button2img,
      links: [
        { name: "Обучение", link: "/learning" },
        { name: "Консультант", link: "/consultant" },
        { name: "Архив", link: "/archive" },
      ],
      type: "large",
    },
    {
      id: 3,
      titleName: "Магазин",
      titleLink: "/shop",
      img: button3img,
      links: [
        { name: "Рулетка", link: "/roulette" },
        { name: "События", link: "/events" },
        { name: "Валюта", link: "/currency" },
      ],
      type: "large",
    },
    {
      id: 4,
      titleLink: "/offers",
      titleName: "Предложения",
      img: smallbuttonimg1,
      type: "small",
    },
    {
      id: 5,
      titleLink: "/administration",
      titleName: "Администрация",
      img: smallbuttonimg2,
      type: "small",
    },
    {
      id: 6,
      titleLink: "/bestiary",
      titleName: "Бестиарий",
      img: smallbuttonimg3,
      type: "small",
    },
    {
      id: 7,
      titleLink: "/findaplayer",
      titleName: "Поиск игрока",
      img: smallbuttonimg4,
      type: "small",
    },
  ];

  const sliderData: SliderPage[] = [
    {
      index: 1,
      title: "Мы открываемся!",
      description: "Все что нужно знать о запуске проекта",
      link: "/sliderlink1",
      img: sliderImg1,
      tag: "Технобук",
    },
    {
      index: 2,
      title: "Мы открываемся!2",
      description: "Все что нужно знать о запуске проекта2",
      link: "/sliderlink2",
      img: sliderImg1,
      tag: "Технобук",
    },
    {
      index: 3,
      title: "Мы открываемся!3",
      description: "Все что нужно знать о запуске проекта3",
      link: "/sliderlink3",
      img: sliderImg1,
      tag: "Технобук",
    },
    {
      index: 4,
      title: "Мы открываемся!4",
      description: "Все что нужно знать о запуске проекта",
      link: "/sliderlink4",
      img: sliderImg1,
      tag: "Технобук",
    },
  ];

  const largeButtons = buttonsData.filter((button) => button.type === "large");
  const smallButtons = buttonsData.filter((button) => button.type === "small");

  return (
    <>
      {/*
        Main grid: left column = large navigation cards, right column = the
        promo slider with the latest-posts feed tucked underneath it.
        Each card sits in a fixed-height block wrapper that force-sizes its
        direct child (`[&>*]:h-full [&>*]:w-full`). Because the wrapper is a
        plain block (not a grid), the legacy `grid-column` / `grid-row` rules
        baked into the Button/Slider SCSS are inert, and each child fills the
        wrapper via `height:100%` against its fixed height.
      */}
      <section className="grid grid-cols-1 lg:grid-cols-[40%_55%] gap-8 lg:gap-x-[5%] lg:gap-y-[60px] lg:items-stretch mb-16 lg:mb-24">
        {/* Left column: large navigation cards + the small nav cards stacked
            beneath them. The small-cards group grows (`flex-1`) to consume the
            leftover height so that, when the grid stretches this column to match
            the taller right column, the bottom of the last small card lines up
            with the bottom of the last post in the feed. */}
        <div className="flex flex-col gap-8 lg:gap-[60px]">
          {largeButtons.map((buttonData) => (
            <div
              key={buttonData.id}
              className="h-[150px] sm:h-[185px] [&>*]:h-full [&>*]:w-full"
            >
              <Button data={buttonData} />
            </div>
          ))}

          <div className="flex flex-col gap-4 sm:gap-6 flex-1">
            {smallButtons.map((buttonData) => (
              <div
                key={buttonData.id}
                className="flex-1 min-h-[70px] sm:min-h-[80px] [&>*]:h-full [&>*]:w-full"
              >
                <Button data={buttonData} />
              </div>
            ))}
          </div>
        </div>

        {/* Right column: promo slider + latest roleplay posts feed */}
        <div className="flex flex-col gap-8 lg:gap-[60px]">
          <div className="h-[280px] sm:h-[360px] lg:h-[430px] [&>*]:h-full [&>*]:w-full">
            <Slider pages={sliderData} />
          </div>

          <LatestRoleplayPosts />
        </div>
      </section>

      <Stats />
    </>
  );
}
