/* app.js — dashboard logic v4 */

// ── Chart instances ─────────────────────────────────────────
let tempChart = null;
let complianceChart = null;

// ── Scroll-safe DOM helpers ─────────────────────────────────
function setHtml(id, html) {
  const el = document.getElementById(id);
  if (el && el.innerHTML !== html) el.innerHTML = html;
}

// ── Architecture diagram — 4-layer per PDF architecture ────
// Layer 01: Sensor/Perception  — LTAT devices with TMP112 sensors
// Layer 02: Gateway            — IGD (hub/store), CCVE (vehicle), CCIE (incubator)
// Layer 03: Cloud              — Cloud Platform, Alert Engine (24/7 dispatch), Audit Chain
// Layer 04: Application        — Web Dashboard, Mobile/Field View
function renderArchDiagram(overview, gateways, analytics, auditCount) {
  const el = document.getElementById("arch-diagram");
  if (!el) return;

  const fh = overview.facility_health || [];
  const gwMap = {};
  (gateways || []).forEach(g => { gwMap[g.facility_id] = g; });

  // ── Layer 01: LTAT sensor nodes (one per facility/location) ──
  const sensorNodes = fh.map(f => {
    const dot = f.status === "healthy" ? "healthy" : f.status === "watch" ? "warning" : "critical";
    const ltat = f.device_count || 0;
    const devLabel = f.facility_type === "transit" ? "CCVE sensors \u00b7 GPS/Beidou"
                   : f.facility_type === "clinic"   ? "CCIE sensors \u00b7 portable"
                                                    : "LTAT sensors \u00b7 TMP112 \u00d75";
    return '<div class="arch-node">'
      + '<span class="arch-node-dot status-dot ' + dot + '"></span>'
      + '<div>'
      + '<div class="arch-node-name">' + f.id.replace("FAC-","") + '</div>'
      + '<div class="arch-node-sub">' + ltat + 'x sensor \u00b7 ' + devLabel + ' \u00b7 ' + f.region + '</div>'
      + '</div></div>';
  }).join("");

  // ── Layer 02: Gateway nodes — classified by facility type ──
  // IGD  = Intelligent Gateway Device   (regional_hub, cold_storage)
  // CCVE = Cold-Chain Vehicle Equipment (transit → GPS-tracked truck)
  // CCIE = Cold-Chain Incubator Equip.  (clinic   → portable field unit)
  const igdNodes = fh
    .filter(f => f.facility_type !== "transit" && f.facility_type !== "clinic")
    .map(f => {
      const gw = gwMap[f.id];
      if (!gw) return "";
      const dot = gw.status === "online" ? "healthy" : gw.status === "degraded" ? "warning" : "critical";
      return '<div class="arch-node">'
        + '<span class="arch-node-dot status-dot ' + dot + '"></span>'
        + '<div>'
        + '<div class="arch-node-name">IGD: ' + gw.id + '</div>'
        + '<div class="arch-node-sub">' + gw.status + ' \u00b7 buf=' + gw.buffered_packets + ' \u00b7 ' + gw.model + ' FW' + gw.firmware_version + '</div>'
        + '</div></div>';
    }).join("");

  const ccveNodes = fh
    .filter(f => f.facility_type === "transit")
    .map(f => {
      const gw = gwMap[f.id];
      if (!gw) return "";
      const dot = gw.status === "online" ? "healthy" : gw.status === "degraded" ? "warning" : "critical";
      return '<div class="arch-node" style="border-color:rgba(96,165,250,.35)">'
        + '<span class="arch-node-dot status-dot ' + dot + '"></span>'
        + '<div>'
        + '<div class="arch-node-name" style="color:var(--info)">CCVE: ' + gw.id + '</div>'
        + '<div class="arch-node-sub">Vehicle \u00b7 GPS/Beidou \u00b7 buf=' + gw.buffered_packets + ' \u00b7 ' + gw.status + '</div>'
        + '</div></div>';
    }).join("");

  const ccieNodes = fh
    .filter(f => f.facility_type === "clinic")
    .map(f => {
      const gw = gwMap[f.id];
      if (!gw) return "";
      const dot = gw.status === "online" ? "healthy" : gw.status === "degraded" ? "warning" : "critical";
      return '<div class="arch-node" style="border-color:rgba(52,211,153,.25)">'
        + '<span class="arch-node-dot status-dot ' + dot + '"></span>'
        + '<div>'
        + '<div class="arch-node-name" style="color:var(--healthy)">CCIE: ' + gw.id + '</div>'
        + '<div class="arch-node-sub">Incubator \u00b7 Portable field unit \u00b7 buf=' + gw.buffered_packets + ' \u00b7 ' + gw.status + '</div>'
        + '</div></div>';
    }).join("");

  const allGwNodes = igdNodes + ccveNodes + ccieNodes
    || '<div class="arch-node"><span class="arch-node-dot status-dot offline"></span><div><div class="arch-node-name">No gateways yet</div></div></div>';

  // ── Layer 03: Cloud metrics ─────────────────────────────────
  const pkts       = analytics ? analytics.kpis.packets : 0;
  const compliance = analytics ? analytics.kpis.compliance_rate_pct : 0;
  const incidents  = analytics ? analytics.kpis.incident_count : 0;
  const openInc    = analytics ? analytics.kpis.open_incidents : 0;
  const notifCount = analytics
    ? analytics.delivery_channels.reduce((s, d) => s + d.total, 0) : 0;
  const auditStr   = auditCount != null ? auditCount : "\u2014";

  const emptyNode = '<div class="arch-node"><span class="arch-node-dot status-dot offline"></span>'
    + '<div><div class="arch-node-name">No devices yet</div></div></div>';

  el.innerHTML = '<div class="arch-layers">'

    + '<div class="arch-layer">'
    + '<div class="arch-layer-label">Layer 01<br><span style="font-size:.65rem">Sensor /</span><br><span style="font-size:.65rem">Perception</span></div>'
    + '<div class="arch-nodes">' + (sensorNodes || emptyNode) + '</div>'
    + '</div>'

    + '<div class="arch-arrow">'
    + '\u21d5 2.4 GHz wireless \u00b7 CH583M microcontroller \u00b7 1-min sampling \u00b7 TMP112 accuracy &lt;0.3 \u00b0C \u00b7 low-power sleep mode'
    + '</div>'

    + '<div class="arch-layer">'
    + '<div class="arch-layer-label">Layer 02<br><span style="font-size:.65rem">Gateway</span></div>'
    + '<div class="arch-nodes">' + allGwNodes + '</div>'
    + '</div>'

    + '<div class="arch-arrow">'
    + '\u21d5 4G Cat.1 (EC200U) \u00b7 HTTP POST \u00b7 store-and-forward SQLite buffer \u00b7 packet loss target &lt;2%'
    + '</div>'

    + '<div class="arch-layer">'
    + '<div class="arch-layer-label">Layer 03<br><span style="font-size:.65rem">Cloud</span></div>'
    + '<div class="arch-nodes">'
    + '<div class="arch-node">'
    + '<span class="arch-node-dot status-dot healthy"></span>'
    + '<div><div class="arch-node-name">Cloud Platform</div>'
    + '<div class="arch-node-sub">FastAPI + SQLite \u00b7 ' + pkts + ' pkts \u00b7 checksum validation \u00b7 ' + compliance + '% compliant</div>'
    + '</div></div>'
    + '<div class="arch-node" style="border-color:rgba(248,113,113,.4)">'
    + '<span class="arch-node-dot status-dot ' + (openInc > 0 ? "critical" : "healthy") + '"></span>'
    + '<div><div class="arch-node-name" style="color:var(--critical)">Alert Engine</div>'
    + '<div class="arch-node-sub">24/7 dispatch \u00b7 rolling avg (30-min) \u00b7 linear regression \u00b7 ' + incidents + ' incidents \u00b7 ' + notifCount + ' alerts \u2192 SMS + Email</div>'
    + '</div></div>'
    + '<div class="arch-node">'
    + '<span class="arch-node-dot status-dot healthy"></span>'
    + '<div><div class="arch-node-name">Audit Chain</div>'
    + '<div class="arch-node-sub">SHA-256 hash-linked \u00b7 ' + auditStr + ' entries \u00b7 tamper-evident immutable log</div>'
    + '</div></div>'
    + '</div></div>'

    + '<div class="arch-arrow">'
    + '\u21d5 REST API \u00b7 JWT (HS256) \u00b7 role-based access control \u00b7 5 s polling'
    + '</div>'

    + '<div class="arch-layer">'
    + '<div class="arch-layer-label">Layer 04<br><span style="font-size:.65rem">Application</span></div>'
    + '<div class="arch-nodes">'
    + '<div class="arch-node">'
    + '<span class="arch-node-dot status-dot healthy"></span>'
    + '<div><div class="arch-node-name">Web Dashboard</div>'
    + '<div class="arch-node-sub">Live \u00b7 Admin / Manager / Supervisor \u00b7 operations console</div>'
    + '</div></div>'
    + '<div class="arch-node">'
    + '<span class="arch-node-dot status-dot healthy"></span>'
    + '<div><div class="arch-node-name">Mobile / Field View</div>'
    + '<div class="arch-node-sub">Vaccinator scope \u00b7 live sensor readings \u00b7 incident alerts \u00b7 batch lookup</div>'
    + '</div></div>'
    + '</div></div>'

    + '</div>';
}

// ── Temperature chart — fixed height, no collapse ───────────
function renderTempChart(recentPoints) {
  const canvas = document.getElementById("temp-chart");
  if (!canvas) return;

  const wrapper = canvas.parentElement;
  if (wrapper && !wrapper.style.height) wrapper.style.height = "220px";

  const pts    = [...recentPoints].reverse().slice(0, 20);
  const labels = pts.map(p => formatTime(p.recorded_at));
  const temps  = pts.map(p => p.temperature_c);
  const avgs   = pts.map(p => p.rolling_avg_c ?? p.temperature_c);

  if (tempChart) {
    tempChart.data.labels = labels;
    tempChart.data.datasets[0].data = temps;
    tempChart.data.datasets[1].data = avgs;
    tempChart.update("none");
    return;
  }

  const ctx = canvas.getContext("2d");
  tempChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Temperature \u00b0C",
          data: temps,
          borderColor: "#3dd6f5",
          backgroundColor: "rgba(61,214,245,.07)",
          borderWidth: 2,
          pointRadius: 3,
          pointBackgroundColor: "#3dd6f5",
          tension: 0.35,
          fill: true,
        },
        {
          label: "30-min rolling avg",
          data: avgs,
          borderColor: "#fbbf24",
          backgroundColor: "transparent",
          borderWidth: 1.5,
          borderDash: [4, 3],
          pointRadius: 0,
          tension: 0.35,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 0 },
      plugins: {
        legend: { labels: { color: getChartColors().legend, font: { size: 11 } } },
        tooltip: { mode: "index", intersect: false },
      },
      scales: {
        x: {
          ticks: { color: getChartColors().tick, maxTicksLimit: 6, font: { size: 10 } },
          grid: { color: getChartColors().gridFaint },
        },
        y: {
          min: 0, max: 12,
          ticks: { color: getChartColors().tick, font: { size: 10 } },
          grid: { color: getChartColors().grid },
        },
      },
    },
  });
}

// ── Compliance donut ─────────────────────────────────────────
function renderComplianceChart(kpis) {
  const canvas = document.getElementById("compliance-chart");
  if (!canvas) return;
  const rate  = kpis.compliance_rate_pct || 0;
  const color = rate >= 95 ? "#34d399" : rate >= 80 ? "#fbbf24" : "#f87171";

  if (complianceChart) {
    complianceChart.data.datasets[0].data = [rate, 100 - rate];
    complianceChart.data.datasets[0].backgroundColor = [color, getChartColors().donutBg];
    complianceChart.update("none");
    return;
  }

  const ctx = canvas.getContext("2d");
  complianceChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Compliant", "Non-compliant"],
      datasets: [{
        data: [rate, 100 - rate],
        backgroundColor: [color, getChartColors().donutBg],
        borderColor: "transparent",
        borderWidth: 0,
        hoverOffset: 4,
      }],
    },
    options: {
      cutout: "72%",
      responsive: false,
      animation: { duration: 0 },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => c.label + ": " + c.raw.toFixed(1) + "%" } },
      },
    },
    plugins: [{
      id: "centerText",
      afterDraw(chart) {
        const { ctx: c, chartArea: { width, height, left, top } } = chart;
        c.save();
        c.font = "bold 18px Inter, sans-serif";
        c.fillStyle = color;
        c.textAlign = "center";
        c.textBaseline = "middle";
        c.fillText(rate.toFixed(0) + "%", left + width / 2, top + height / 2 - 7);
        c.font = "10px Inter, sans-serif";
        c.fillStyle = getChartColors().centerSub;
        c.fillText("compliant", left + width / 2, top + height / 2 + 10);
        c.restore();
      },
    }],
  });
}

// ── DC Event feed ───────────────────────────────────────────
const EVENT_ICONS = {
  packet_ingested:   "\ud83d\udce1",
  incident_opened:   "\ud83d\udea8",
  incident_resolved: "\u2705",
  alert_multicast:   "\ud83d\udcec",
  system_boot:       "\u26a1",
};

function renderDcFeed(events) {
  const html = (!events || events.length === 0)
    ? '<p class="empty-state">No events yet \u2014 start the simulator.</p>'
    : events.slice(0, 20).map(ev =>
        '<div class="dc-event ' + ev.event_type + '">'
        + '<div class="dc-event-icon">' + (EVENT_ICONS[ev.event_type] || "\u25cf") + '</div>'
        + '<div class="dc-event-body">'
        + '<div class="dc-event-type">' + ev.event_type.replace(/_/g," ") + ' \u00b7 ' + ev.node_id + '</div>'
        + '<div class="dc-event-desc">' + ev.description + '</div>'
        + '</div>'
        + '<div class="dc-event-time">' + formatTime(ev.occurred_at) + '</div>'
        + '</div>'
      ).join("");
  setHtml("dc-feed", html);
}

// ── Gateway grid ────────────────────────────────────────────
function renderGateways(gateways) {
  const html = (!gateways || gateways.length === 0)
    ? '<p class="empty-state">No gateway data.</p>'
    : gateways.map(g => {
        const dot  = g.status === "online" ? "healthy" : g.status === "degraded" ? "warning" : "critical";
        const chip = g.status === "online" ? "online"  : g.status === "degraded" ? "degraded" : "offline";
        const typeLabel = g.facility_type === "transit" ? "CCVE"
                        : g.facility_type === "clinic"  ? "CCIE"
                                                        : "IGD";
        const typeColor = g.facility_type === "transit" ? "var(--info)"
                        : g.facility_type === "clinic"  ? "var(--healthy)"
                                                        : "var(--muted)";
        return '<div style="background:var(--panel);border:1px solid var(--border);border-radius:var(--radius-sm);padding:.85rem 1rem">'
          + '<div style="display:flex;align-items:center;gap:.5rem;margin-bottom:.35rem">'
          + '<span class="status-dot ' + dot + '"></span>'
          + '<span style="font-weight:600;font-size:.85rem">' + g.id + '</span>'
          + '<span style="font-size:.72rem;color:' + typeColor + ';margin-left:.25rem">[' + typeLabel + ']</span>'
          + '<span class="chip ' + chip + '" style="margin-left:auto">' + g.status + '</span>'
          + '</div>'
          + '<div class="ts">' + g.facility_name + '</div>'
          + '<div class="ts" style="margin-top:.2rem">Model: ' + g.model + ' \u00b7 FW ' + g.firmware_version + '</div>'
          + (g.buffered_packets > 0
            ? '<div style="margin-top:.35rem;font-size:.76rem;color:var(--warning)">\u26a0 ' + g.buffered_packets + ' pkts buffered (store-and-forward active)</div>'
            : '<div style="margin-top:.35rem;font-size:.76rem;color:var(--healthy)">\u2713 Buffer empty \u2014 fully synced</div>')
          + '</div>';
      }).join("");
  setHtml("gateway-grid", html);
}

// ── Map — init once, update markers every refresh ──────────
// Fixes: resize(), wait for style load, live marker updates

function _updateMapMarkers(mapboxgl, transit) {
  if (!window._coldTraceMap) return;
  // Remove stale markers
  (window._coldTraceMarkers || []).forEach(m => m.remove());
  window._coldTraceMarkers = [];
  transit.forEach(t => {
    if (!t.longitude || !t.latitude) return;
    const color = tempTone(t.temperature_c) === "critical" ? "#f87171" : "#3dd6f5";
    const marker = new mapboxgl.Marker({ color })
      .setLngLat([t.longitude, t.latitude])
      .setPopup(new mapboxgl.Popup({ offset: 16 }).setHTML(
        '<strong>' + t.device_id + '</strong><br>'
        + t.batch_id + '<br>'
        + formatTemp(t.temperature_c)))
      .addTo(window._coldTraceMap);
    window._coldTraceMarkers.push(marker);
  });
}

async function renderMap(cfg, transit) {
  // Transit list always updates
  const listHtml = transit.length
    ? transit.map(t =>
        '<div class="data-row">'
        + '<div class="data-row-left">'
        + '<div class="row-title">' + t.device_id + '</div>'
        + '<div class="row-sub">' + t.batch_id + ' \u00b7 ' + formatTemp(t.temperature_c) + '</div>'
        + '</div>'
        + '<div class="data-row-right">'
        + '<span class="chip ' + tempTone(t.temperature_c) + '">' + t.facility_id.replace("FAC-","") + '</span>'
        + '<span class="ts">' + formatTime(t.recorded_at) + '</span>'
        + '</div></div>'
      ).join("")
    : '<p class="empty-state">No live transit telemetry.</p>';
  setHtml("transit-list", listHtml);

  const mapStatus = document.getElementById("map-status");
  const mapEl     = document.getElementById("map");

  // ── SVG fallback (no Mapbox token) ─────────────────────────
  if (!cfg.has_mapbox) {
    if (mapStatus) mapStatus.textContent = "SVG fallback \u2014 add MAPBOX_ACCESS_TOKEN in .env for live map.";
    const pts = transit.filter(t => t.latitude && t.longitude);
    mapEl.innerHTML = '<svg viewBox="0 0 400 240" width="100%" style="display:block">'
      + '<rect width="400" height="240" style="fill:var(--bg)" rx="8"/>'
      + '<text x="200" y="18" style="fill:var(--muted)" text-anchor="middle" font-size="10" font-family="Inter,sans-serif">Maharashtra Cold Chain \u2014 CCVE Transit Assets</text>'
      + pts.map(t => {
          const x = Math.round(((t.longitude - 72.5) / 5.0) * 360 + 20);
          const y = Math.round(((21.5 - t.latitude)  / 5.5) * 200 + 20);
          const c = tempTone(t.temperature_c) === "critical" ? "#f87171" : "#3dd6f5";
          return '<circle cx="' + x + '" cy="' + y + '" r="6" fill="' + c + '" opacity=".85"/>'
            + '<text x="' + x + '" y="' + (y+16) + '" style="fill:var(--faint)" text-anchor="middle" font-size="8" font-family="Inter,sans-serif">'
            + t.device_id.replace("LTAT-","") + '</text>';
        }).join("")
      + (!pts.length ? '<text x="200" y="125" style="fill:var(--muted)" text-anchor="middle" font-size="12" font-family="Inter,sans-serif">No transit assets online yet</text>' : "")
      + '</svg>';
    return;
  }

  // ── Mapbox path ─────────────────────────────────────────────
  try {
    const mapboxgl = await ensureMapbox(cfg);
    mapboxgl.accessToken = cfg.mapbox_access_token;

    if (!window._coldTraceMap) {
      // First init — create the map
      const center = transit[0] ? [transit[0].longitude, transit[0].latitude] : [76.5, 19.5];
      window._coldTraceMap = new mapboxgl.Map({
        container: "map",
        style: cfg.mapbox_style,
        center,
        zoom: 5.5,
        attributionControl: false,
      });

      if (mapStatus) mapStatus.textContent = "Live Mapbox \u2014 CCVE vehicle positions.";

      // Wait for style to fully load, THEN add markers + resize
      window._coldTraceMap.on("load", () => {
        window._coldTraceMap.resize();
        _updateMapMarkers(mapboxgl, transit);
      });

      // Belt-and-suspenders resize after paint
      setTimeout(() => {
        if (window._coldTraceMap) window._coldTraceMap.resize();
      }, 400);

    } else {
      // Subsequent refreshes — just update markers (map already loaded)
      _updateMapMarkers(mapboxgl, transit);
    }

  } catch (err) {
    console.error("Mapbox error:", err);
    if (mapEl) mapEl.innerHTML = '<div class="map-placeholder"><div class="map-placeholder-icon">\ud83d\uddfa</div><span>Map unavailable</span></div>';
  }
}

// ── Simulation Controls ─────────────────────────────────────
function simStatus(msg, cls) {
  const el = document.getElementById("sim-status");
  if (!el) return;
  el.className = "sim-status " + (cls || "");
  el.textContent = msg;
}

function simBusy(busy) {
  ["btn-excursion","btn-outage","btn-resolve"].forEach(id => {
    const b = document.getElementById(id);
    if (b) b.disabled = busy;
  });
}

async function postAction(url, successMsg) {
  simStatus("\u23f3 Sending\u2026", "loading");
  simBusy(true);
  try {
    const token = getToken();
    const res = await fetch(url, {
      method: "POST",
      headers: token ? { Authorization: "Bearer " + token } : {},
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    simStatus("\u2713 " + successMsg + " \u2014 " + JSON.stringify(data).slice(0, 120), "ok");
  } catch (err) {
    simStatus("\u2717 Error: " + err.message, "err");
  } finally {
    simBusy(false);
  }
}

async function initSimControls() {
  // Populate device dropdown
  const devSel = document.getElementById("sim-device");
  const gwSel  = document.getElementById("sim-gateway");
  const incSel = document.getElementById("sim-incident");
  if (!devSel) return;

  try {
    const [devices, gateways] = await Promise.all([
      fetchJson("/api/devices"),
      fetchJson("/api/gateways"),
    ]);
    if (devices) {
      devSel.innerHTML = devices.map(d =>
        '<option value="' + d.id + '">' + d.id + ' \u00b7 ' + d.device_type + ' \u00b7 ' + d.facility_name + '</option>'
      ).join("");
    }
    if (gateways) {
      gwSel.innerHTML = gateways.map(g =>
        '<option value="' + g.id + '">' + g.id + ' [' + g.status + ']</option>'
      ).join("");
    }
  } catch (e) { /* ignore — controls still work */ }

  // Wire buttons
  document.getElementById("btn-excursion").addEventListener("click", () => {
    const deviceId = devSel.value;
    const tempC    = document.getElementById("sim-temp").value || "10.5";
    postAction(
      "/api/simulate/excursion?device_id=" + encodeURIComponent(deviceId) + "&temp_c=" + tempC,
      "Excursion injected \u2192 incident created"
    );
  });

  document.getElementById("btn-outage").addEventListener("click", () => {
    const gwId = gwSel.value;
    postAction(
      "/api/simulate/outage?gateway_id=" + encodeURIComponent(gwId),
      "Gateway toggled \u2192 buffer updated"
    );
  });

  document.getElementById("btn-resolve").addEventListener("click", () => {
    const incId = incSel.value;
    if (!incId) { simStatus("\u26a0 No open incident selected", "err"); return; }
    postAction("/api/incidents/" + encodeURIComponent(incId) + "/resolve", "Incident resolved");
  });
}

// Refresh open incidents dropdown each cycle
function refreshIncidentDropdown(incidents) {
  const incSel = document.getElementById("sim-incident");
  if (!incSel) return;
  const open = (incidents || []).filter(i => i.status === "open");
  if (!open.length) {
    incSel.innerHTML = '<option value="">— no open incidents —</option>';
  } else {
    incSel.innerHTML = open.map(i =>
      '<option value="' + i.id + '">' + i.id + ' \u00b7 ' + i.device_id + ' \u00b7 ' + i.severity + '</option>'
    ).join("");
  }
}

// ── Main ────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  requireSession();

  document.getElementById("logout-btn").addEventListener("click", logout);
  document.getElementById("go-operator").addEventListener("click", () => window.location.href = "/operator");

  // Init simulation controls once
  initSimControls();
  document.getElementById("go-report").addEventListener("click", () => window.location.href = "/reports/executive");
  document.getElementById("download-summary").addEventListener("click", () => downloadProtected("/api/reports/export/summary.csv", "coldtrace-summary.csv"));
  document.getElementById("download-incidents").addEventListener("click", () => downloadProtected("/api/reports/export/incidents.csv", "coldtrace-incidents.csv"));

  async function refresh() {
    try {
      const [cfg, me, overview, telemetry, incidents, notifications, batches, analytics, transit, dcEvents, gateways] =
        await Promise.all([
          fetchJson("/api/public/config"),
          fetchJson("/api/auth/me"),
          fetchJson("/api/overview"),
          fetchJson("/api/telemetry/recent?limit=15"),
          fetchJson("/api/incidents?limit=10"),
          fetchJson("/api/notifications?limit=10"),
          fetchJson("/api/batches"),
          fetchJson("/api/reports/analytics"),
          fetchJson("/api/transit/latest"),
          fetchJson("/api/dc-events?limit=20"),
          fetchJson("/api/gateways"),
        ]);

      if (!me) return;

      // ── User pill ──────────────────────────────────────────
      const pillEl = document.getElementById("user-pill");
      const pillHtml = '<span class="user-pip"></span> ' + me.full_name + ' <span style="color:var(--faint)">\u00b7 ' + me.role + '</span>';
      if (pillEl.innerHTML !== pillHtml) pillEl.innerHTML = pillHtml;

      // ── KPI strip ──────────────────────────────────────────
      const s  = overview.summary;
      const kk = analytics.kpis;
      setHtml("kpi-grid", [
        kpiCard("Facilities",     s.facilities,                           "Active scope",      "\ud83c\udfe5"),
        kpiCard("Telemetry Pkts", s.telemetry_packets,                    "Total ingested",    "\ud83d\udce1"),
        kpiCard("Open Incidents", s.open_incidents,                       "Needs attention",   "\ud83d\udea8", s.open_incidents > 0 ? "critical" : "healthy"),
        kpiCard("Low Battery",    s.low_battery_nodes,                    "Battery risk",      "\ud83d\udd0b", s.low_battery_nodes > 0 ? "warning" : "healthy"),
        kpiCard("Transit Assets", s.active_transit_assets,                "Live CCVE/CCIE",   "\ud83d\ude9a"),
        kpiCard("Avg Temp",       s.average_temperature_c != null ? s.average_temperature_c + " \u00b0C" : "\u2014", "Fleet average", "\ud83c\udf21\ufe0f", s.average_temperature_c != null ? tempTone(s.average_temperature_c) : ""),
        kpiCard("Compliance",     kk.compliance_rate_pct + "%",           "In-range packets",  "\u2705", kk.compliance_rate_pct >= 95 ? "healthy" : kk.compliance_rate_pct >= 80 ? "warning" : "critical"),
        kpiCard("Excursions",     kk.excursions,                          "Temp breaches",     "\u26a0\ufe0f", kk.excursions > 0 ? "warning" : ""),
      ].join(""));

      // ── Architecture diagram (real data) ──────────────────
      const auditCount = dcEvents ? dcEvents.length : 0;
      renderArchDiagram(overview, gateways, analytics, auditCount);

      // ── Charts ────────────────────────────────────────────
      renderTempChart(analytics.recent_points);
      renderComplianceChart(kk);

      // ── DC event feed ─────────────────────────────────────
      renderDcFeed(dcEvents);

      // ── Sync open incident dropdown in sim controls ───────
      refreshIncidentDropdown(incidents);

      // ── Gateways ──────────────────────────────────────────
      renderGateways(gateways);

      // ── Facility health ───────────────────────────────────
      setHtml("facility-health", overview.facility_health.map(f => {
        const typeLabel = f.facility_type === "transit" ? "CCVE"
                        : f.facility_type === "clinic"  ? "CCIE" : "IGD";
        return '<div class="data-row">'
          + '<div class="data-row-left">'
          + '<div class="row-title" style="display:flex;align-items:center;gap:.5rem">'
          + '<span class="status-dot ' + f.status + '"></span> ' + f.name
          + '</div>'
          + '<div class="row-sub">' + f.region + ' \u00b7 ' + f.device_count + ' device(s) \u00b7 ' + typeLabel + ' \u00b7 GW: <span style="color:' + (f.gateway_status === "online" ? "var(--healthy)" : "var(--warning)") + '">' + (f.gateway_status || "unknown") + '</span></div>'
          + '</div>'
          + '<span class="chip ' + f.status + '">' + f.status + '</span>'
          + '</div>';
      }).join("") || '<p class="empty-state">No facility data.</p>');

      // ── Incident mix ──────────────────────────────────────
      const mix = overview.incident_mix || {};
      setHtml("incident-mix", Object.keys(mix).length
        ? Object.entries(mix).map(([k, v]) =>
            '<div style="display:flex;justify-content:space-between;align-items:center;padding:.5rem 0;border-bottom:1px solid var(--border)">'
            + '<span style="font-size:.84rem;color:var(--muted)">' + k.replace(/_/g," ") + '</span>'
            + '<span class="chip ' + (k.includes("battery") ? "warning" : "critical") + '">' + v + '</span>'
            + '</div>'
          ).join("")
        : '<p class="empty-state" style="padding:.75rem 0">No active incidents \ud83c\udf89</p>');

      // ── Telemetry table ───────────────────────────────────
      setHtml("telemetry-body", (telemetry||[]).map(t => {
        const tone = tempTone(t.temperature_c, t.min_temp_c, t.max_temp_c);
        const bat  = batteryTone(t.battery_voltage);
        return '<tr>'
          + '<td class="ts">' + formatTime(t.recorded_at) + '</td>'
          + '<td><span style="font-weight:500">' + t.device_id + '</span><br><span class="ts">' + (t.facility_name || t.facility_id) + '</span></td>'
          + '<td><span class="chip ' + tone + '">' + formatTemp(t.temperature_c) + '</span></td>'
          + '<td class="ts">' + (t.humidity_pct != null ? t.humidity_pct.toFixed(1) + "%" : "\u2014") + '</td>'
          + '<td><span class="chip ' + bat + '">' + (t.battery_voltage != null ? t.battery_voltage.toFixed(2) + " V" : "\u2014") + '</span></td>'
          + '<td class="ts">' + t.transport_mode + '</td>'
          + '</tr>';
      }).join("") || '<tr><td colspan="6" style="text-align:center;padding:1.2rem;color:var(--faint)">No telemetry \u2014 start the simulator</td></tr>');

      // ── Incidents ─────────────────────────────────────────
      setHtml("incidents-list", (incidents||[]).length
        ? incidents.map(i =>
            '<div class="data-row">'
            + '<div class="data-row-left">'
            + '<div class="row-title">' + i.incident_type.replace(/_/g," ") + '</div>'
            + '<div class="row-sub">' + i.device_id + ' \u00b7 ' + i.facility_name + '</div>'
            + '<div class="ts" style="margin-top:.2rem">' + i.reason + '</div>'
            + '</div>'
            + '<div class="data-row-right">'
            + '<span class="chip ' + i.severity + '">' + i.severity + '</span>'
            + '<span class="chip ' + (i.status === "open" ? "critical" : "healthy") + '">' + i.status + '</span>'
            + '</div></div>'
          ).join("")
        : '<p class="empty-state">No incidents logged.</p>');

      // ── Notifications ─────────────────────────────────────
      setHtml("notification-list", (notifications||[]).length
        ? notifications.map(n =>
            '<div class="data-row">'
            + '<div class="data-row-left">'
            + '<div class="row-title">' + n.channel.toUpperCase() + ' \u00b7 ' + n.provider + '</div>'
            + '<div class="row-sub">' + n.recipient + '</div>'
            + '</div>'
            + '<div class="data-row-right">'
            + '<span class="chip ' + (n.status === "failed" ? "critical" : "healthy") + '">' + n.status + '</span>'
            + '<span class="ts">' + formatTime(n.sent_at) + '</span>'
            + '</div></div>'
          ).join("")
        : '<p class="empty-state">Notifications appear after first incident.</p>');

      // ── Batches ───────────────────────────────────────────
      setHtml("batch-list", (batches||[]).map(b =>
        '<div class="trace-row">'
        + '<div style="min-width:0;flex:1">'
        + '<div style="font-weight:600;font-size:.88rem">' + b.id + '</div>'
        + '<div class="ts">' + b.vaccine_name + ' \u00b7 ' + b.manufacturer + (b.lot_number ? ' \u00b7 LOT: ' + b.lot_number : "") + '</div>'
        + '</div>'
        + '<span class="trace-origin">' + b.origin_name + '</span>'
        + '<span class="trace-arrow">\u2192</span>'
        + '<span class="trace-dest">' + b.destination_name + '</span>'
        + '<div class="trace-meta">'
        + '<span class="chip ' + (b.status === "in_transit" ? "info" : b.status === "delivered" ? "healthy" : "neutral") + '">' + b.status.replace(/_/g," ") + '</span>'
        + '<span class="ts">' + (b.doses_remaining || b.doses_total) + ' doses</span>'
        + '</div></div>'
      ).join("") || '<p class="empty-state">No batch data.</p>');

      // ── Map — init once, markers update every refresh ────
      await renderMap(cfg, transit);

    } catch (err) {
      console.error("Refresh error:", err);
    }
  }

  await refresh();
  setInterval(refresh, 5000);
});

function kpiCard(label, value, sub, icon, cls) {
  icon = icon || "";
  cls  = cls  || "";
  return '<div class="kpi-card">'
    + '<div class="kpi-icon">' + icon + '</div>'
    + '<div class="kpi-label">' + label + '</div>'
    + '<div class="kpi-value ' + cls + '">' + value + '</div>'
    + '<div class="kpi-sub">' + sub + '</div>'
    + '</div>';
}

// ── Theme change — live-update Chart.js colors ───────────────
window.addEventListener("themechange", () => {
  const c = getChartColors();
  if (tempChart) {
    tempChart.options.plugins.legend.labels.color        = c.legend;
    tempChart.options.scales.x.ticks.color              = c.tick;
    tempChart.options.scales.x.grid.color               = c.gridFaint;
    tempChart.options.scales.y.ticks.color              = c.tick;
    tempChart.options.scales.y.grid.color               = c.grid;
    tempChart.update();
  }
  if (complianceChart) {
    // donut background segment adapts; signal arc stays as-is (semantic color)
    const ds = complianceChart.data.datasets[0];
    ds.backgroundColor = [ds.backgroundColor[0], c.donutBg];
    complianceChart.update();
  }
});
