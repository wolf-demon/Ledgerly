import axios from "axios";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API });

export default api;

export const formatGBP = (n) => {
  if (n === null || n === undefined || isNaN(n)) return "£0.00";
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  return `${sign}£${abs.toLocaleString("en-GB", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
};

export const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];
