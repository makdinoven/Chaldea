import s from './WorldPage.module.scss'
import axios from "axios";
import {useEffect} from "react";
import Map from "./Map/Map.jsx";

export default function WorldPage() {

    useEffect(() => {
        axios
            .get('http://localhost:8006/locations/locations/lookup', {
                headers: {
                    Accept: 'application/json',
                },
            })
            .then((response) => {
                console.log(response.data);
            })
            .catch((error) => console.log(error));
    }, []);


    return (
        <>
            <h1>World page</h1>
            <Map />
            </>)

}