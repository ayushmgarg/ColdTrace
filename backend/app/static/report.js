document.addEventListener("DOMContentLoaded", async () => {
  requireSession();
  const goDashboard = document.getElementById("go-dashboard");
  if (goDashboard) {
    goDashboard.addEventListener("click", () => {
      window.location.href = "/";
    });
  }

  const analytics = await fetchJson("/api/reports/analytics");
  document.getElementById("report-kpis").innerHTML = [
    metricCard("Compliance", `${analytics.kpis.compliance_rate_pct}%`, "Telemetry within safe range"),
    metricCard("Incidents", analytics.kpis.incident_count, "Total logged incidents"),
    metricCard("Open", analytics.kpis.open_incidents, "Currently unresolved"),
    metricCard("Excursions", analytics.kpis.excursions, "Temperature excursions"),
    metricCard("Avg Temp", analytics.kpis.average_temperature_c ?? "--", "Average observed temperature"),
    metricCard("Avg Battery", analytics.kpis.average_battery_v ?? "--", "Average battery voltage"),
  ].join("");

  document.getElementById("report-facilities").innerHTML = analytics.facility_performance.length
    ? analytics.facility_performance.map((item) => `
        <div class="list-card">
          <div>
            <strong>${item.facility_name}</strong>
            <p>${item.excursions} excursions · lowest battery ${item.lowest_battery_v} V</p>
          </div>
          <span class="chip ${item.excursions > 0 ? "warning" : "healthy"}">${item.avg_temp_c} C</span>
        </div>
      `).join("")
    : `<p class="empty-state">No facility analytics yet.</p>`;

  document.getElementById("report-delivery").innerHTML = analytics.delivery_channels.length
    ? analytics.delivery_channels.map((item) => `
        <div class="list-card">
          <div>
            <strong>${item.channel.toUpperCase()} via ${item.provider}</strong>
            <p>${item.status}</p>
          </div>
          <span class="chip healthy">${item.total}</span>
        </div>
      `).join("")
    : `<p class="empty-state">Notification analytics will appear once incidents are created.</p>`;

  document.getElementById("report-points").innerHTML = analytics.recent_points.length
    ? analytics.recent_points.map((item) => `
        <div class="list-card">
          <div>
            <strong>${item.device_id}</strong>
            <p>${formatTemp(item.temperature_c)} · ${item.battery_voltage.toFixed(2)} V</p>
          </div>
          <span class="subtle">${formatTime(item.recorded_at)}</span>
        </div>
      `).join("")
    : `<p class="empty-state">No telemetry points recorded yet.</p>`;
});
