import axios from "axios";

const charClient = axios.create({
  baseURL: "",
  timeout: 10000,
});

export const fetchCharacters = async () => {
  const { data } = await charClient.get("/characters/list");
  return data;
};