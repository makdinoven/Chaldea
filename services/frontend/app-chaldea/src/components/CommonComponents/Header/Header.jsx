import React from "react";

import Menu from "./Menu/Menu";

import styles from "./Header.module.scss";

import logo from "../../../assets/logo.png";
import menuImg1 from "../../../assets/menu1.png";
import menuImg2 from "../../../assets/menu2.png";
import menuImg3 from "../../../assets/menuImg.png";
import { Link, useNavigate } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";

export default function Header() {
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const { username, avatar, character } = useSelector((state) => state.user);

  // if (!username) {
  //   dispatch(logout());
  //   navigate("/");
  // }

  const menuData = [
    {
      id: 1,
      menuButtons: [
        { name: "Сообщения", link: "/messages" },
        { name: "Поддержка", link: "/support" },
        { name: "Профиль", link: "/profile" },
        { name: "Выход", link: "/" },
      ],
      img: avatar ? avatar : menuImg1,
      title: username,
    },
    {
      id: 2,
      menuButtons: character
        ? [{ name: "Профиль", link: "/" }]
        : [
            { name: "Создать", link: "/createCharacter" },
            { name: "Выбрать", link: "/selectCharacter" },
          ],
      img: character ? character.avatar : menuImg2,
      title: character?.name,
    },
    {
      id: 3,
      menuButtons: [{ name: "Заявки", link: "/requestsPage" }],
      img: menuImg3,
      title: "Заявки",
    },
  ];

  return (
    <>
      <header className={styles.header}>
        <div className={styles.menu_container_left}>
          {menuData.slice(0, 2).map((menu) => (
            <Menu
              key={menu.id}
              title={menu.title}
              menuButtons={menu.menuButtons}
              backgroundImg={menu.img}
            />
          ))}
        </div>
        <Link to={"/home"} className={styles.logo}>
          <img src={logo} alt="Logo" />
        </Link>

        <div className={styles.menu_container_right}>
          {character && (
            <Menu
              title={character.current_location.name}
              menuButtons={[
                {
                  name: "Перейти",
                  link: `/location/${character.current_location.id}`,
                },
              ]}
              backgroundImg={character.current_location.image_url}
            />
          )}

          {menuData.slice(2).map((menu) => (
            <Menu
              key={menu.id}
              title={menu.title}
              menuButtons={menu.menuButtons}
              backgroundImg={menu.img}
            />
          ))}
        </div>
      </header>
    </>
  );
}
