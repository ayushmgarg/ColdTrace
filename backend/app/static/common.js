/* common.js — shared auth + fetch helpers */
const TOKEN_KEY = "ct_token";
const USER_KEY  = "ct_user";

function saveSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}
function getToken() { return localStorage.getItem(TOKEN_KEY); }
function getUser()  { try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; } }
function clearSession() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); }

function logout() {
  clearSession();
  window.location.href = "/login";
}

function requireSession() {
  if (!getToken()) { window.location.href = "/login"; }
}

async function fetchJson(url) {
  const token = getToken();
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (res.status === 401) { logout(); return null; }
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${url}`);
  return res.json();
}

async function downloadProtected(url, filename) {
  const token = getToken();
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) return;
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
}

function formatTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatTemp(t) {
  if (t == null) return "—";
  return t.toFixed(1) + " °C";
}

function tempTone(t, min = 2, max = 8) {
  if (t < min || t > max) return "critical";
  if (t < min + 0.5 || t > max - 0.5) return "warning";
  return "healthy";
}

function batteryTone(v) {
  if (v < 2.1) return "critical";
  if (v < 2.5) return "warning";
  return "healthy";
}

async function ensureMapbox(cfg) {
  return new Promise((resolve, reject) => {
    if (window.mapboxgl) { resolve(window.mapboxgl); return; }
    const script = document.createElement("script");
    script.src = "https://api.mapbox.com/mapbox-gl-js/v3.3.0/mapbox-gl.js";
    script.onload = () => resolve(window.mapboxgl);
    script.onerror = reject;
    document.head.appendChild(script);
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "https://api.mapbox.com/mapbox-gl-js/v3.3.0/mapbox-gl.css";
    document.head.appendChild(link);
  });
}
