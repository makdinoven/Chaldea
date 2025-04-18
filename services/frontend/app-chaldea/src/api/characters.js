import axios from "axios";

const charClient = axios.create({
  baseURL: "http://4452515-co41851.twc1.net:8005",
  timeout: 10000,
});

export const fetchCharacters = async () => {
  const { data } = await charClient.get("/characters/list");
  return data;
};