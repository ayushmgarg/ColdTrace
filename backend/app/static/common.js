const TOKEN_KEY = "coldtrace_token";
const USER_KEY = "coldtrace_user";

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function getUser() {
  const raw = localStorage.getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

function setSession(accessToken, user) {
  localStorage.setItem(TOKEN_KEY, accessToken);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    clearSession();
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response;
}

async function fetchJson(url, options = {}) {
  const response = await apiFetch(url, options);
  return response.json();
}

function requireSession() {
  if (!getToken()) {
    window.location.href = "/login";
    throw new Error("Missing session");
  }
}

function logout() {
  clearSession();
  window.location.href = "/login";
}

function formatTemp(value) {
  return `${Number(value).toFixed(2)} C`;
}

function formatTime(value) {
  return new Date(value).toLocaleString();
}

function chipToneForTemperature(value, min = 2, max = 8) {
  if (value < min || value > max) return "critical";
  if (value < min + 0.75 || value > max - 0.75) return "warning";
  return "healthy";
}

function metricCard(label, value, hint) {
  return `
    <article class="metric-card">
      <p>${label}</p>
      <strong>${value ?? "--"}</strong>
      <span>${hint}</span>
    </article>
  `;
}

async function downloadProtected(url, filename) {
  const response = await apiFetch(url);
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(objectUrl);
}

async function ensureMapbox(publicConfig) {
  if (!publicConfig.has_mapbox || !publicConfig.mapbox_access_token) return null;
  if (window.mapboxgl) return window.mapboxgl;

  const css = document.createElement("link");
  css.rel = "stylesheet";
  css.href = "https://api.mapbox.com/mapbox-gl-js/v3.4.0/mapbox-gl.css";
  document.head.appendChild(css);

  await new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://api.mapbox.com/mapbox-gl-js/v3.4.0/mapbox-gl.js";
    script.onload = resolve;
    script.onerror = reject;
    document.body.appendChild(script);
  });

  return window.mapboxgl;
}
