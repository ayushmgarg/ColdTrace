/* app.js — dashboard logic v3 */

// ── Chart instances ─────────────────────────────────────────
let tempChart = null;
let complianceChart = null;

// ── Scroll-safe DOM helpers ─────────────────────────────────
// Only update inner text/class if value changed — never replace innerHTML on
// containers the user might be scrolling inside.
function setHtml(id, html) {
  const el = document.getElementById(id);
  if (el && el.innerHTML !== html) el.innerHTML = html;
}

// ── Architecture diagram — uses REAL live data ──────────────
function renderArchDiagram(overview, gateways, analytics, auditCount) {
  const el = document.getElementById("arch-diagram");
  if (!el) return;

  const fh = overview.facility_health || [];
  const gwMap = {};
  (gateways || []).forEach(g => gwMap[g.facility_id] = g);

  // Layer 1: real sensor nodes from API
  const sensorNodes = fh.map(f => {
    const dot = f.status === "healthy" ? "healthy" : f.status === "watch" ? "warning" : "critical";
    const gw = gwMap[f.id];
    const ltat = f.device_count || 0;
    return `<div class="arch-node">
      <span class="arch-node-dot status-dot ${dot}"></span>
      <div>
        <div class="arch-node-name">${f.id.replace("FAC-","")}</div>
        <div class="arch-node-sub">${ltat} LTAT · ${f.region}</div>
      </div>
    </div>`;
  }).join("");

  // Layer 2: real gateway nodes from API
  const gwNodes = fh.map(f => {
    const gw = gwMap[f.id];
    const st  = gw ? gw.status : "unknown";
    const buf = gw ? gw.buffered_packets : 0;
    const dot = st === "online" ? "healthy" : st === "degraded" ? "warning" : "critical";
    const fw  = gw ? gw.firmware_version : "?";
    return `<div class="arch-node">
      <span class="arch-node-dot status-dot ${dot}"></span>
      <div>
        <div class="arch-node-name">${gw ? gw.id : "—"}</div>
        <div class="arch-node-sub">${st} · buf=${buf} · FW ${fw}</div>
      </div>
    </div>`;
  }).join("");

  // Layer 3: real cloud stats from analytics
  const pkts       = analytics ? analytics.kpis.packets : 0;
  const compliance = analytics ? analytics.kpis.compliance_rate_pct : 0;
  const incidents  = analytics ? analytics.kpis.incident_count : 0;
  const auditStr   = auditCount != null ? auditCount : "—";

  // Layer 4: real browser/notification stats
  const notifCount = analytics
    ? analytics.delivery_channels.reduce((s, d) => s + d.total, 0)
    : 0;

  el.innerHTML = `<div class="arch-layers">

    <div class="arch-layer">
      <div class="arch-layer-label">Layer 1<br>Sensors</div>
      <div class="arch-nodes">${sensorNodes || '<div class="arch-node"><span class="arch-node-dot status-dot offline"></span><div><div class="arch-node-name">No devices yet</div></div></div>'}</div>
    </div>

    <div class="arch-arrow">↕ 2.4 GHz wireless · store-and-forward MQTT</div>

    <div class="arch-layer">
      <div class="arch-layer-label">Layer 2<br>Gateways</div>
      <div class="arch-nodes">${gwNodes || '<div class="arch-node"><span class="arch-node-dot status-dot offline"></span><div><div class="arch-node-name">No gateways</div></div></div>'}</div>
    </div>

    <div class="arch-arrow">↕ 4G Cat.1 HTTP POST · packet loss target &lt;2%</div>

    <div class="arch-layer">
      <div class="arch-layer-label">Layer 3<br>Cloud</div>
      <div class="arch-nodes">
        <div class="arch-node">
          <span class="arch-node-dot status-dot healthy"></span>
          <div>
            <div class="arch-node-name">FastAPI + SQLite</div>
            <div class="arch-node-sub">${pkts} packets · ${compliance}% compliant · ${incidents} incidents</div>
          </div>
        </div>
        <div class="arch-node">
          <span class="arch-node-dot status-dot healthy"></span>
          <div>
            <div class="arch-node-name">Audit Chain</div>
            <div class="arch-node-sub">SHA-256 hash-linked · ${auditStr} entries</div>
          </div>
        </div>
      </div>
    </div>

    <div class="arch-arrow">↕ REST API · 5 s polling · role-based JWT</div>

    <div class="arch-layer">
      <div class="arch-layer-label">Layer 4<br>App</div>
      <div class="arch-nodes">
        <div class="arch-node">
          <span class="arch-node-dot status-dot healthy"></span>
          <div>
            <div class="arch-node-name">Web Dashboard</div>
            <div class="arch-node-sub">Live · 4 roles · this browser session</div>
          </div>
        </div>
        <div class="arch-node">
          <span class="arch-node-dot status-dot ${notifCount > 0 ? "healthy" : "offline"}"></span>
          <div>
            <div class="arch-node-name">Alert Multicast</div>
            <div class="arch-node-sub">${notifCount} notifications sent · SMS + Email</div>
          </div>
        </div>
      </div>
    </div>

  </div>`;
}

// ── Temperature chart — fixed height, no collapse ───────────
function renderTempChart(recentPoints) {
  const canvas = document.getElementById("temp-chart");
  if (!canvas) return;

  // Fix: set explicit pixel height on the wrapper so chart never collapses
  const wrapper = canvas.parentElement;
  if (wrapper && !wrapper.style.height) wrapper.style.height = "220px";

  const pts    = [...recentPoints].reverse().slice(0, 20);
  const labels = pts.map(p => formatTime(p.recorded_at));
  const temps  = pts.map(p => p.temperature_c);
  const avgs   = pts.map(p => p.rolling_avg_c ?? p.temperature_c);

  if (tempChart) {
    // Update data in-place — never destroy/recreate (causes flash + scroll jump)
    tempChart.data.labels = labels;
    tempChart.data.datasets[0].data = temps;
    tempChart.data.datasets[1].data = avgs;
    tempChart.update("none"); // "none" = no animation on update
    return;
  }

  const ctx = canvas.getContext("2d");
  tempChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Temperature °C",
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
      animation: { duration: 0 }, // no animation at all — prevents chart falling
      plugins: {
        legend: { labels: { color: "#7aacb8", font: { size: 11 } } },
        tooltip: { mode: "index", intersect: false },
      },
      scales: {
        x: {
          ticks: { color: "#3d6a78", maxTicksLimit: 6, font: { size: 10 } },
          grid: { color: "rgba(255,255,255,.03)" },
        },
        y: {
          min: 0, max: 12,
          ticks: { color: "#3d6a78", font: { size: 10 } },
          grid: { color: "rgba(255,255,255,.04)" },
        },
      },
    },
  });
}

// ── Compliance donut — fixed, no animation on update ─────────
function renderComplianceChart(kpis) {
  const canvas = document.getElementById("compliance-chart");
  if (!canvas) return;
  const rate  = kpis.compliance_rate_pct || 0;
  const color = rate >= 95 ? "#34d399" : rate >= 80 ? "#fbbf24" : "#f87171";

  if (complianceChart) {
    complianceChart.data.datasets[0].data = [rate, 100 - rate];
    complianceChart.data.datasets[0].backgroundColor = [color, "rgba(255,255,255,.05)"];
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
        backgroundColor: [color, "rgba(255,255,255,.05)"],
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
        c.fillStyle = "#3d6a78";
        c.fillText("compliant", left + width / 2, top + height / 2 + 10);
        c.restore();
      },
    }],
  });
}

// ── DC Event feed ───────────────────────────────────────────
const EVENT_ICONS = {
  packet_ingested:   "📡",
  incident_opened:   "🚨",
  incident_resolved: "✅",
  alert_multicast:   "📬",
  system_boot:       "⚡",
};

function renderDcFeed(events) {
  const html = (!events || events.length === 0)
    ? `<p class="empty-state">No events yet — start the simulator.</p>`
    : events.slice(0, 20).map(ev => `
        <div class="dc-event ${ev.event_type}">
          <div class="dc-event-icon">${EVENT_ICONS[ev.event_type] || "●"}</div>
          <div class="dc-event-body">
            <div class="dc-event-type">${ev.event_type.replace(/_/g," ")} · ${ev.node_id}</div>
            <div class="dc-event-desc">${ev.description}</div>
          </div>
          <div class="dc-event-time">${formatTime(ev.occurred_at)}</div>
        </div>
      `).join("");
  setHtml("dc-feed", html);
}

// ── Gateway grid ────────────────────────────────────────────
function renderGateways(gateways) {
  const html = (!gateways || gateways.length === 0)
    ? `<p class="empty-state">No gateway data.</p>`
    : gateways.map(g => {
        const dot  = g.status === "online" ? "healthy" : g.status === "degraded" ? "warning" : "critical";
        const chip = g.status === "online" ? "online"  : g.status === "degraded" ? "degraded" : "offline";
        return `
          <div style="background:var(--panel);border:1px solid var(--border);border-radius:var(--radius-sm);padding:.85rem 1rem">
            <div style="display:flex;align-items:center;gap:.5rem;margin-bottom:.35rem">
              <span class="status-dot ${dot}"></span>
              <span style="font-weight:600;font-size:.85rem">${g.id}</span>
              <span class="chip ${chip}" style="margin-left:auto">${g.status}</span>
            </div>
            <div class="ts">${g.facility_name}</div>
            <div class="ts" style="margin-top:.2rem">Model: ${g.model} · FW ${g.firmware_version}</div>
            ${g.buffered_packets > 0
              ? `<div style="margin-top:.35rem;font-size:.76rem;color:var(--warning)">⚠ ${g.buffered_packets} pkts buffered (store-and-forward active)</div>`
              : `<div style="margin-top:.35rem;font-size:.76rem;color:var(--healthy)">✓ Buffer empty — fully synced</div>`}
          </div>`;
      }).join("");
  setHtml("gateway-grid", html);
}

// ── Map — render once only ──────────────────────────────────
async function renderMap(cfg, transit) {
  const listHtml = transit.length
    ? transit.map(t => `
        <div class="data-row">
          <div class="data-row-left">
            <div class="row-title">${t.device_id}</div>
            <div class="row-sub">${t.batch_id} · ${formatTemp(t.temperature_c)}</div>
          </div>
          <div class="data-row-right">
            <span class="chip ${tempTone(t.temperature_c)}">${t.facility_id.replace("FAC-","")}</span>
            <span class="ts">${formatTime(t.recorded_at)}</span>
          </div>
        </div>`).join("")
    : `<p class="empty-state">No live transit telemetry.</p>`;
  setHtml("transit-list", listHtml);

  const mapStatus = document.getElementById("map-status");
  const mapEl     = document.getElementById("map");

  if (!cfg.has_mapbox) {
    if (mapStatus) mapStatus.textContent = "SVG fallback — add Mapbox token in .env for live map.";
    const pts = transit.filter(t => t.latitude && t.longitude);
    mapEl.innerHTML = `
      <svg viewBox="0 0 400 240" width="100%" style="display:block">
        <rect width="400" height="240" fill="#0b1a22" rx="8"/>
        <text x="200" y="18" fill="#3d6a78" text-anchor="middle" font-size="10" font-family="Inter,sans-serif">Maharashtra Cold Chain — Transit Assets</text>
        ${pts.map(t => {
          const x = Math.round(((t.longitude - 72.5) / 5.0) * 360 + 20);
          const y = Math.round(((21.5 - t.latitude)  / 5.5) * 200 + 20);
          const c = tempTone(t.temperature_c) === "critical" ? "#f87171" : "#3dd6f5";
          return `<circle cx="${x}" cy="${y}" r="6" fill="${c}" opacity=".85"/>
                  <text x="${x}" y="${y+16}" fill="#7aacb8" text-anchor="middle" font-size="8" font-family="Inter,sans-serif">${t.device_id.replace("LTAT-","")}</text>`;
        }).join("")}
        ${!pts.length ? '<text x="200" y="125" fill="#3d6a78" text-anchor="middle" font-size="12" font-family="Inter,sans-serif">No transit assets online</text>' : ""}
      </svg>`;
    return;
  }

  try {
    const mapboxgl = await ensureMapbox(cfg);
    mapboxgl.accessToken = cfg.mapbox_access_token;
    if (window._coldTraceMap) { window._coldTraceMap.remove(); }
    const center = transit[0] ? [transit[0].longitude, transit[0].latitude] : [75.5, 19.5];
    window._coldTraceMap = new mapboxgl.Map({ container: "map", style: cfg.mapbox_style, center, zoom: 5.5 });
    if (mapStatus) mapStatus.textContent = "Live Mapbox transport map.";
    transit.forEach(t => {
      if (!t.longitude || !t.latitude) return;
      const color = tempTone(t.temperature_c) === "critical" ? "#f87171" : "#3dd6f5";
      new mapboxgl.Marker({ color })
        .setLngLat([t.longitude, t.latitude])
        .setPopup(new mapboxgl.Popup({ offset: 16 }).setHTML(
          `<strong>${t.device_id}</strong><br>${t.batch_id}<br>${formatTemp(t.temperature_c)}`))
        .addTo(window._coldTraceMap);
    });
  } catch {
    mapEl.innerHTML = `<div class="map-placeholder"><div class="map-placeholder-icon">🗺</div><span>Map unavailable</span></div>`;
  }
}

// ── Main ────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  requireSession();

  document.getElementById("logout-btn").addEventListener("click", logout);
  document.getElementById("go-operator").addEventListener("click", () => window.location.href = "/operator");
  document.getElementById("go-report").addEventListener("click", () => window.location.href = "/reports/executive");
  document.getElementById("download-summary").addEventListener("click", () => downloadProtected("/api/reports/export/summary.csv", "coldtrace-summary.csv"));
  document.getElementById("download-incidents").addEventListener("click", () => downloadProtected("/api/reports/export/incidents.csv", "coldtrace-incidents.csv"));

  let mapDone     = false;
  let firstRender = true;

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

      // ── User pill (small update, no scroll impact) ──────────
      const pillEl = document.getElementById("user-pill");
      const pillHtml = `<span class="user-pip"></span> ${me.full_name} <span style="color:var(--faint)">· ${me.role}</span>`;
      if (pillEl.innerHTML !== pillHtml) pillEl.innerHTML = pillHtml;

      // ── KPI strip ───────────────────────────────────────────
      const s  = overview.summary;
      const kk = analytics.kpis;
      setHtml("kpi-grid", [
        kpiCard("Facilities",      s.facilities,                          "Active scope",       "🏥"),
        kpiCard("Telemetry Pkts",  s.telemetry_packets,                   "Total ingested",     "📡"),
        kpiCard("Open Incidents",  s.open_incidents,                      "Needs attention",    "🚨", s.open_incidents > 0 ? "critical" : "healthy"),
        kpiCard("Low Battery",     s.low_battery_nodes,                   "Battery risk",       "🔋", s.low_battery_nodes > 0 ? "warning" : "healthy"),
        kpiCard("Transit Assets",  s.active_transit_assets,               "Live mobile nodes",  "🚚"),
        kpiCard("Avg Temp",        s.average_temperature_c != null ? s.average_temperature_c + " °C" : "—", "Fleet average", "🌡️", s.average_temperature_c != null ? tempTone(s.average_temperature_c) : ""),
        kpiCard("Compliance",      kk.compliance_rate_pct + "%",          "In-range packets",   "✅", kk.compliance_rate_pct >= 95 ? "healthy" : kk.compliance_rate_pct >= 80 ? "warning" : "critical"),
        kpiCard("Excursions",      kk.excursions,                         "Temp breaches",      "⚠️", kk.excursions > 0 ? "warning" : ""),
      ].join(""));

      // ── Architecture diagram (real data) ────────────────────
      // Fetch audit count from dc_events as proxy
      const auditCount = dcEvents ? dcEvents.length : 0;
      renderArchDiagram(overview, gateways, analytics, auditCount);

      // ── Charts ──────────────────────────────────────────────
      renderTempChart(analytics.recent_points);
      renderComplianceChart(kk);

      // ── DC feed ─────────────────────────────────────────────
      renderDcFeed(dcEvents);

      // ── Gateways ────────────────────────────────────────────
      renderGateways(gateways);

      // ── Facility health ─────────────────────────────────────
      setHtml("facility-health", overview.facility_health.map(f => `
        <div class="data-row">
          <div class="data-row-left">
            <div class="row-title" style="display:flex;align-items:center;gap:.5rem">
              <span class="status-dot ${f.status}"></span> ${f.name}
            </div>
            <div class="row-sub">${f.region} · ${f.device_count} device(s) · GW: <span style="color:${f.gateway_status==="online"?"var(--healthy)":"var(--warning)"}">${f.gateway_status||"unknown"}</span></div>
          </div>
          <span class="chip ${f.status}">${f.status}</span>
        </div>`).join("") || `<p class="empty-state">No facility data.</p>`);

      // ── Incident mix ────────────────────────────────────────
      const mix = overview.incident_mix || {};
      setHtml("incident-mix", Object.keys(mix).length
        ? Object.entries(mix).map(([k, v]) => `
            <div style="display:flex;justify-content:space-between;align-items:center;padding:.5rem 0;border-bottom:1px solid var(--border)">
              <span style="font-size:.84rem;color:var(--muted)">${k.replace(/_/g," ")}</span>
              <span class="chip ${k.includes("battery")?"warning":"critical"}">${v}</span>
            </div>`).join("")
        : `<p class="empty-state" style="padding:.75rem 0">No active incidents 🎉</p>`);

      // ── Telemetry table ─────────────────────────────────────
      // Use setHtml — table body is not user-scrollable so safe to replace
      setHtml("telemetry-body", (telemetry||[]).map(t => {
        const tone = tempTone(t.temperature_c, t.min_temp_c, t.max_temp_c);
        const bat  = batteryTone(t.battery_voltage);
        return `<tr>
          <td class="ts">${formatTime(t.recorded_at)}</td>
          <td><span style="font-weight:500">${t.device_id}</span><br><span class="ts">${t.facility_name||t.facility_id}</span></td>
          <td><span class="chip ${tone}">${formatTemp(t.temperature_c)}</span></td>
          <td class="ts">${t.humidity_pct!=null?t.humidity_pct.toFixed(1)+"%":"—"}</td>
          <td><span class="chip ${bat}">${t.battery_voltage!=null?t.battery_voltage.toFixed(2)+" V":"—"}</span></td>
          <td class="ts">${t.transport_mode}</td>
        </tr>`;
      }).join("") || `<tr><td colspan="6" style="text-align:center;padding:1.2rem;color:var(--faint)">No telemetry — start the simulator</td></tr>`);

      // ── Incidents ───────────────────────────────────────────
      setHtml("incidents-list", (incidents||[]).length
        ? incidents.map(i => `
            <div class="data-row">
              <div class="data-row-left">
                <div class="row-title">${i.incident_type.replace(/_/g," ")}</div>
                <div class="row-sub">${i.device_id} · ${i.facility_name}</div>
                <div class="ts" style="margin-top:.2rem">${i.reason}</div>
              </div>
              <div class="data-row-right">
                <span class="chip ${i.severity}">${i.severity}</span>
                <span class="chip ${i.status==="open"?"critical":"healthy"}">${i.status}</span>
              </div>
            </div>`).join("")
        : `<p class="empty-state">No incidents logged.</p>`);

      // ── Notifications ───────────────────────────────────────
      setHtml("notification-list", (notifications||[]).length
        ? notifications.map(n => `
            <div class="data-row">
              <div class="data-row-left">
                <div class="row-title">${n.channel.toUpperCase()} · ${n.provider}</div>
                <div class="row-sub">${n.recipient}</div>
              </div>
              <div class="data-row-right">
                <span class="chip ${n.status==="failed"?"critical":"healthy"}">${n.status}</span>
                <span class="ts">${formatTime(n.sent_at)}</span>
              </div>
            </div>`).join("")
        : `<p class="empty-state">Notifications appear after first incident.</p>`);

      // ── Batches ─────────────────────────────────────────────
      setHtml("batch-list", (batches||[]).map(b => `
        <div class="trace-row">
          <div style="min-width:0;flex:1">
            <div style="font-weight:600;font-size:.88rem">${b.id}</div>
            <div class="ts">${b.vaccine_name} · ${b.manufacturer}${b.lot_number?" · LOT: "+b.lot_number:""}</div>
          </div>
          <span class="trace-origin">${b.origin_name}</span>
          <span class="trace-arrow">→</span>
          <span class="trace-dest">${b.destination_name}</span>
          <div class="trace-meta">
            <span class="chip ${b.status==="in_transit"?"info":b.status==="delivered"?"healthy":"neutral"}">${b.status.replace(/_/g," ")}</span>
            <span class="ts">${b.doses_remaining||b.doses_total} doses</span>
          </div>
        </div>`).join("") || `<p class="empty-state">No batch data.</p>`);

      // ── Map — render exactly once ───────────────────────────
      if (!mapDone) { await renderMap(cfg, transit); mapDone = true; }

      firstRender = false;

    } catch (err) {
      console.error("Refresh error:", err);
    }
  }

  await refresh();
  setInterval(refresh, 5000);
});

function kpiCard(label, value, sub, icon = "", cls = "") {
  return `<div class="kpi-card">
    <div class="kpi-icon">${icon}</div>
    <div class="kpi-label">${label}</div>
    <div class="kpi-value ${cls}">${value}</div>
    <div class="kpi-sub">${sub}</div>
  </div>`;
}
