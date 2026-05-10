/* report.js — executive report + viva evidence page */

let barChart = null;
let incChart = null;

document.addEventListener("DOMContentLoaded", async () => {
  requireSession();
  document.getElementById("go-dashboard").addEventListener("click", () => window.location.href = "/");

  const [analytics, auditEntries] = await Promise.all([
    fetchJson("/api/reports/analytics"),
    fetchJson("/api/audit-log?limit=20"),
  ]);

  const kpis = analytics.kpis;

  // ── KPI strip ──────────────────────────────────────────────
  const compColor = kpis.compliance_rate_pct >= 95 ? "healthy"
                  : kpis.compliance_rate_pct >= 80 ? "warning" : "critical";
  document.getElementById("report-kpis").innerHTML = [
    kpiCard("Compliance Rate",   kpis.compliance_rate_pct + "%",      "Packets within 2–8 °C",   "✅", compColor),
    kpiCard("Total Packets",     kpis.packets,                         "Telemetry ingested",       "📡"),
    kpiCard("Total Incidents",   kpis.incident_count,                  "All time",                "🚨"),
    kpiCard("Open Incidents",    kpis.open_incidents,                  "Unresolved now",           "⚠️", kpis.open_incidents > 0 ? "critical" : "healthy"),
    kpiCard("Temp Excursions",   kpis.excursions,                      "Range breaches",           "🌡️", kpis.excursions > 0 ? "warning" : ""),
    kpiCard("Battery Events",    kpis.battery_events,                  "Low-voltage alerts",       "🔋"),
    kpiCard("Avg Temperature",   kpis.average_temperature_c != null ? kpis.average_temperature_c + " °C" : "—", "Fleet mean", "🌡️"),
    kpiCard("Avg Battery",       kpis.average_battery_v != null ? kpis.average_battery_v + " V" : "—",          "Fleet mean", "⚡"),
  ].join("");

  // ── Bar chart: compliance vs excursions per facility ───────
  const facPerf = analytics.facility_performance || [];
  const barCtx  = document.getElementById("report-bar-chart").getContext("2d");
  barChart = new Chart(barCtx, {
    type: "bar",
    data: {
      labels: facPerf.map(f => f.facility_name.replace(" Cold Hub","").replace(" Transit","").replace(" Clinic","")),
      datasets: [
        { label: "Excursions", data: facPerf.map(f => f.excursions),
          backgroundColor: "rgba(248,113,113,.55)", borderColor: "#f87171", borderWidth: 1, borderRadius: 4 },
        { label: "Avg Temp °C", data: facPerf.map(f => f.avg_temp_c),
          backgroundColor: "rgba(61,214,245,.4)", borderColor: "#3dd6f5", borderWidth: 1, borderRadius: 4,
          yAxisID: "y2" },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 0 },
      plugins: { legend: { labels: { color: getChartColors().legend, font: { size: 11 } } } },
      scales: {
        x: { ticks: { color: getChartColors().tick, font: { size: 10 } }, grid: { color: getChartColors().gridFaint } },
        y:  { ticks: { color: getChartColors().tick, font: { size: 10 } }, grid: { color: getChartColors().grid }, title: { display: true, text: "Excursions", color: getChartColors().tick, font: { size: 10 } } },
        y2: { position: "right", ticks: { color: getChartColors().tick, font: { size: 10 } }, grid: { drawOnChartArea: false }, title: { display: true, text: "Avg Temp \u00b0C", color: getChartColors().tick, font: { size: 10 } } },
      },
    },
  });

  // ── Doughnut: incident type breakdown ──────────────────────
  const incCtx = document.getElementById("report-inc-chart").getContext("2d");
  incChart = new Chart(incCtx, {
    type: "doughnut",
    data: {
      labels: ["Temp Excursions", "Battery Events", "Resolved"],
      datasets: [{
        data: [kpis.excursions, kpis.battery_events,
               Math.max(0, kpis.incident_count - kpis.open_incidents)],
        backgroundColor: ["rgba(248,113,113,.7)", "rgba(251,191,36,.7)", "rgba(52,211,153,.5)"],
        borderColor: ["#f87171","#fbbf24","#34d399"],
        borderWidth: 1, hoverOffset: 6,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "58%",
      animation: { duration: 0 },
      plugins: {
        legend: { position: "bottom", labels: { color: getChartColors().legend, font: { size: 11 }, padding: 12 } },
      },
    },
  });

  // ── Facility performance bars ───────────────────────────────
  const maxExcursions = Math.max(1, ...facPerf.map(f => f.excursions));
  document.getElementById("report-perf-bars").innerHTML = facPerf.length
    ? facPerf.map(f => {
        const pct = (f.excursions / maxExcursions) * 100;
        const color = f.excursions === 0 ? "#34d399" : f.excursions < 3 ? "#fbbf24" : "#f87171";
        return `
          <div class="perf-bar-row">
            <div class="perf-bar-label" title="${f.facility_name}">${f.facility_name}</div>
            <div class="perf-bar-track">
              <div class="perf-bar-fill" style="width:${pct}%;background:${color}"></div>
            </div>
            <div class="perf-bar-val">${f.excursions} exc · ${f.avg_temp_c} °C</div>
          </div>
        `;
      }).join("")
    : `<p class="empty-state">No facility data yet.</p>`;

  // ── Delivery channels ───────────────────────────────────────
  const delivery = analytics.delivery_channels || [];
  document.getElementById("report-delivery").innerHTML = delivery.length
    ? delivery.map(d => `
        <div class="data-row">
          <div class="data-row-left">
            <div class="row-title">${d.channel.toUpperCase()} · ${d.provider}</div>
            <div class="row-sub">${d.status}</div>
          </div>
          <span class="chip ${d.status === "failed" ? "critical" : "healthy"}">${d.total}</span>
        </div>
      `).join("")
    : `<p class="empty-state">No notifications yet — incidents trigger these.</p>`;

  // ── Recent telemetry table ──────────────────────────────────
  const pts = analytics.recent_points || [];
  document.getElementById("report-points-body").innerHTML = pts.length
    ? pts.slice(0, 10).map(p => {
        const tone = tempTone(p.temperature_c);
        const bat  = batteryTone(p.battery_voltage);
        return `<tr>
          <td style="font-weight:500">${p.device_id}</td>
          <td><span class="chip ${tone}">${formatTemp(p.temperature_c)}</span></td>
          <td><span class="chip ${bat}">${p.battery_voltage != null ? p.battery_voltage.toFixed(2)+" V" : "—"}</span></td>
          <td class="ts">${formatTime(p.recorded_at)}</td>
        </tr>`;
      }).join("")
    : `<tr><td colspan="4" class="empty-state" style="text-align:center;padding:1rem">No telemetry yet</td></tr>`;

  // ── Audit chain — real SHA-256 hash-linked entries ─────────
  const auditEl = document.getElementById("report-audit");
  if (auditEntries && auditEntries.length > 0) {
    auditEl.innerHTML =
      '<table>'
      + '<thead><tr>'
      + '<th>Action</th><th>Entity</th><th>Entry Hash (SHA-256)</th><th>Prev Hash</th><th>Time</th>'
      + '</tr></thead>'
      + '<tbody>'
      + auditEntries.slice(0, 15).map(e => {
          const hashShort = e.entry_hash ? e.entry_hash.slice(0, 16) + "\u2026" : "\u2014";
          const prevShort = e.previous_hash ? e.previous_hash.slice(0, 12) + "\u2026" : "\u2014";
          const cls = e.action === "opened" ? "critical"
                    : e.action === "resolved" ? "healthy"
                    : e.action === "login" ? "info"
                    : "neutral";
          return '<tr>'
            + '<td><span class="chip ' + cls + '">' + e.action + '</span></td>'
            + '<td style="font-size:.78rem;color:var(--muted)">' + e.entity_type + ' / ' + e.entity_id.slice(0,20) + '</td>'
            + '<td style="font-family:monospace;font-size:.72rem;color:var(--accent)">' + hashShort + '</td>'
            + '<td style="font-family:monospace;font-size:.72rem;color:var(--faint)">' + prevShort + '</td>'
            + '<td class="ts">' + formatTime(e.created_at) + '</td>'
            + '</tr>';
        }).join("")
      + '</tbody></table>'
      + '<p style="font-size:.75rem;color:var(--faint);margin-top:.75rem">'
      + '\u2191 SHA-256 hash chain: each entry embeds previous entry\'s hash. Any tampering breaks the chain. '
      + auditEntries.length + ' entries shown (most recent first).'
      + '</p>';
  } else {
    auditEl.innerHTML = '<p class="empty-state">Audit entries appear after system events. Start the simulator to generate data.</p>';
  }
});

function kpiCard(label, value, sub, icon = "", cls = "") {
  return `<div class="kpi-card">
    <div class="kpi-icon">${icon}</div>
    <div class="kpi-label">${label}</div>
    <div class="kpi-value ${cls}">${value}</div>
    <div class="kpi-sub">${sub}</div>
  </div>`;
}

// ── Theme change — live-update report chart colors ────────────
window.addEventListener("themechange", () => {
  const c = getChartColors();
  if (barChart) {
    barChart.options.plugins.legend.labels.color       = c.legend;
    barChart.options.scales.x.ticks.color             = c.tick;
    barChart.options.scales.x.grid.color              = c.gridFaint;
    barChart.options.scales.y.ticks.color             = c.tick;
    barChart.options.scales.y.grid.color              = c.grid;
    barChart.options.scales.y.title.color             = c.tick;
    barChart.options.scales.y2.ticks.color            = c.tick;
    barChart.options.scales.y2.title.color            = c.tick;
    barChart.update();
  }
  if (incChart) {
    incChart.options.plugins.legend.labels.color = c.legend;
    incChart.update();
  }
});
