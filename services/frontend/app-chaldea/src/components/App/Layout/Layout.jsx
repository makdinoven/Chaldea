import s from './Layout.module.scss'
import Header from "../../CommonComponents/Header/Header.jsx";
import {Outlet} from "react-router-dom";

export default function Layout() {

    return (
            <div className={s.container}>
                <Header />
                <Outlet />
            </div>

    )
};