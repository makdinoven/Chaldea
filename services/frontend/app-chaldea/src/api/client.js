import axios from "axios";

const client = axios.create({
  baseURL: "http://4452515-co41851.twc1.net:8004/inventory",
  withCredentials: true,
  timeout: 10000,
});

client.interceptors.response.use(
  (r) => r,
  (e) => {
    if (e.response) {
      // возврат читаемого текста ошибки
      throw new Error(e.response.data?.detail || e.response.statusText);
    }
    throw e;
  }
);

export default client;