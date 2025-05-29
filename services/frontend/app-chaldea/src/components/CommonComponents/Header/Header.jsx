import React, { useEffect } from "react";

import Menu from "./Menu/Menu";

import styles from "./Header.module.scss";

import logo from "../../../assets/logo.png";
import menuImg1 from "../../../assets/menu1.png";
import menuImg2 from "../../../assets/menu2.png";
import menuImg3 from "../../../assets/menuImg.png";
import { Link, useLocation } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";
import { getMe } from "../../../redux/slices/userSlice.js";

export default function Header() {
  const location = useLocation();
  const dispatch = useDispatch();
  const { username, avatar, character, role } = useSelector(
    (state) => state.user,
  );

  useEffect(() => {
    dispatch(getMe());
  }, [location.pathname]);

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
  ];

  menuData.push({
    id: 3,
    menuButtons: [
      { name: "Заявки", link: "requestsPage" },
      { name: "Айтемы", link: "/admin/items" },
      { name: "Локации", link: "/admin/locations" },
    ],
    img: menuImg3,
    title: "Админка",
  });

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
          {character?.current_location && (
            <Menu
              title={character.current_location?.name}
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
