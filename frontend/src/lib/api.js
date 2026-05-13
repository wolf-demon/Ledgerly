import axios from "axios";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API });

// Global error interceptor — caller code can still `try/catch` and surface
// user-friendly toasts, but we make sure that an unhandled rejection here
// downgrades to a `warn` log (which React's dev error overlay does NOT
// intercept) instead of an `error` log. This stops the full-screen red
// overlay appearing on transient 403s / network blips during project
// switches, deletes, or upstream proxy hiccups (e.g. Cloudflare bot challenge).
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const method = (error?.config?.method || "").toUpperCase();
    const url = error?.config?.url || "";
    // eslint-disable-next-line no-console
    console.warn(`[api] ${method} ${url} → ${status || error?.message || "network"}`);
    return Promise.reject(error);
  },
);

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
