async function renderMap(publicConfig, transitLocations) {
  const mapStatus = document.getElementById("map-status");
  const mapElement = document.getElementById("map");
  const transitList = document.getElementById("transit-list");

  transitList.innerHTML = transitLocations.length
    ? transitLocations.map((item) => `
        <div class="list-card">
          <div>
            <strong>${item.device_id}</strong>
            <p>${item.batch_id} · ${formatTemp(item.temperature_c)}</p>
          </div>
          <div class="right-col">
            <span class="chip ${chipToneForTemperature(item.temperature_c)}">${item.facility_id}</span>
            <span class="subtle">${formatTime(item.recorded_at)}</span>
          </div>
        </div>
      `).join("")
    : `<p class="empty-state">No live transit telemetry right now.</p>`;

  if (!publicConfig.has_mapbox) {
    mapStatus.textContent = "Add a Mapbox token in .env to unlock the live transport map.";
    mapElement.innerHTML = "<div class='map-placeholder'>Mapbox token not configured</div>";
    return;
  }

  try {
    const mapboxgl = await ensureMapbox(publicConfig);
    mapboxgl.accessToken = publicConfig.mapbox_access_token;
    const firstPoint = transitLocations[0] || { longitude: 73.8567, latitude: 18.5204 };
    const map = new mapboxgl.Map({
      container: "map",
      style: publicConfig.mapbox_style,
      center: [firstPoint.longitude, firstPoint.latitude],
      zoom: 5.8,
    });
    mapStatus.textContent = "Live transport assets rendered with Mapbox.";

    transitLocations.forEach((item) => {
      if (item.longitude == null || item.latitude == null) return;
      const popup = new mapboxgl.Popup({ offset: 18 }).setHTML(
        `<strong>${item.device_id}</strong><br/>${item.batch_id}<br/>${formatTemp(item.temperature_c)}`
      );
      new mapboxgl.Marker({ color: item.temperature_c > 8 || item.temperature_c < 2 ? "#ff7b72" : "#74d8eb" })
        .setLngLat([item.longitude, item.latitude])
        .setPopup(popup)
        .addTo(map);
    });
  } catch (error) {
    mapStatus.textContent = "Mapbox script could not load in this environment.";
    mapElement.innerHTML = "<div class='map-placeholder'>Map unavailable</div>";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  requireSession();

  document.getElementById("logout-btn").addEventListener("click", logout);
  document.getElementById("go-operator").addEventListener("click", () => {
    window.location.href = "/operator";
  });
  document.getElementById("go-report").addEventListener("click", () => {
    window.location.href = "/reports/executive";
  });
  document.getElementById("download-summary").addEventListener("click", () => {
    downloadProtected("/api/reports/export/summary.csv", "coldtrace-summary.csv");
  });
  document.getElementById("download-incidents").addEventListener("click", () => {
    downloadProtected("/api/reports/export/incidents.csv", "coldtrace-incidents.csv");
  });

  async function refresh() {
    const [publicConfig, me, overview, telemetry, incidents, notifications, batches, analytics, transit] =
      await Promise.all([
        fetchJson("/api/public/config"),
        fetchJson("/api/auth/me"),
        fetchJson("/api/overview"),
        fetchJson("/api/telemetry/recent?limit=12"),
        fetchJson("/api/incidents?limit=8"),
        fetchJson("/api/notifications?limit=8"),
        fetchJson("/api/batches"),
        fetchJson("/api/reports/analytics"),
        fetchJson("/api/transit/latest"),
      ]);

    document.getElementById("user-pill").textContent = `${me.full_name} · ${me.role}`;

    document.getElementById("summary-cards").innerHTML = [
      metricCard("Facilities", overview.summary.facilities, "Active cold-chain scope"),
      metricCard("Packets", overview.summary.telemetry_packets, "Telemetry ingested"),
      metricCard("Open Incidents", overview.summary.open_incidents, "Needs attention"),
      metricCard("Low Battery", overview.summary.low_battery_nodes, "Battery risk"),
      metricCard("Transit Assets", overview.summary.active_transit_assets, "Live mobile nodes"),
      metricCard("Avg Temp", overview.summary.average_temperature_c ?? "--", "Current fleet average"),
    ].join("");

    document.getElementById("analytics-kpis").innerHTML = [
      metricCard("Compliance", `${analytics.kpis.compliance_rate_pct}%`, "In-range telemetry share"),
      metricCard("Excursions", analytics.kpis.excursions, "Temperature breaches"),
      metricCard("Battery Events", analytics.kpis.battery_events, "Low-battery detections"),
      metricCard("Avg Battery", analytics.kpis.average_battery_v ?? "--", "Latest monitored state"),
    ].join("");

    document.getElementById("delivery-mix").innerHTML = analytics.delivery_channels.length
      ? analytics.delivery_channels.map((item) => `
          <div class="list-card">
            <div>
              <strong>${item.channel.toUpperCase()} · ${item.provider}</strong>
              <p>${item.status}</p>
            </div>
            <span class="chip healthy">${item.total}</span>
          </div>
        `).join("")
      : `<p class="empty-state">Notification delivery data will appear after the first incident.</p>`;

    document.getElementById("facility-health").innerHTML = overview.facility_health.map((item) => `
      <div class="list-card">
        <div>
          <strong>${item.name}</strong>
          <p>${item.region} · ${item.device_count} devices</p>
        </div>
        <span class="chip ${item.status}">${item.status}</span>
      </div>
    `).join("");

    const mixEntries = Object.entries(overview.incident_mix || {});
    document.getElementById("incident-mix").innerHTML = mixEntries.length
      ? mixEntries.map(([label, value]) => `
          <div class="mix-row">
            <span>${label.replaceAll("_", " ")}</span>
            <strong>${value}</strong>
          </div>
        `).join("")
      : `<p class="empty-state">No active incidents right now.</p>`;

    document.getElementById("recent-points").innerHTML = analytics.recent_points.length
      ? analytics.recent_points.slice(0, 8).map((item) => `
          <div class="list-card">
            <div>
              <strong>${item.device_id}</strong>
              <p>${formatTemp(item.temperature_c)} · ${item.battery_voltage.toFixed(2)} V</p>
            </div>
            <span class="subtle">${formatTime(item.recorded_at)}</span>
          </div>
        `).join("")
      : `<p class="empty-state">No trend points yet.</p>`;

    document.getElementById("telemetry-body").innerHTML = telemetry.map((item) => `
      <tr>
        <td>${formatTime(item.recorded_at)}</td>
        <td>${item.device_id}</td>
        <td>${item.facility_id}</td>
        <td><span class="chip ${chipToneForTemperature(item.temperature_c, item.min_temp_c, item.max_temp_c)}">${formatTemp(item.temperature_c)}</span></td>
        <td>${item.humidity_pct.toFixed(1)}%</td>
        <td>${item.battery_voltage.toFixed(2)} V</td>
        <td>${item.transport_mode}</td>
      </tr>
    `).join("");

    document.getElementById("incidents-list").innerHTML = incidents.length
      ? incidents.map((item) => `
          <div class="list-card">
            <div>
              <strong>${item.incident_type.replaceAll("_", " ")}</strong>
              <p>${item.device_id} · ${item.facility_name}</p>
              <p>${item.reason}</p>
            </div>
            <div class="right-col">
              <span class="chip ${item.severity}">${item.severity}</span>
              <span class="subtle">${item.status}</span>
            </div>
          </div>
        `).join("")
      : `<p class="empty-state">No incidents logged.</p>`;

    document.getElementById("notification-list").innerHTML = notifications.length
      ? notifications.map((item) => `
          <div class="list-card">
            <div>
              <strong>${item.channel.toUpperCase()} · ${item.provider}</strong>
              <p>${item.recipient}</p>
            </div>
            <div class="right-col">
              <span class="chip ${item.status === "failed" ? "critical" : "healthy"}">${item.status}</span>
              <span class="subtle">${formatTime(item.sent_at)}</span>
            </div>
          </div>
        `).join("")
      : `<p class="empty-state">Notifications will appear after the first incident.</p>`;

    document.getElementById("batch-list").innerHTML = batches.map((item) => `
      <div class="trace-card">
        <div>
          <strong>${item.id}</strong>
          <p>${item.vaccine_name} · ${item.manufacturer}</p>
        </div>
        <div class="trace-line">
          <span>${item.origin_name}</span>
          <span class="arrow">→</span>
          <span>${item.destination_name}</span>
        </div>
        <div class="right-col">
          <span class="chip healthy">${item.status}</span>
          <span class="subtle">${item.doses_total} doses</span>
        </div>
      </div>
    `).join("");

    await renderMap(publicConfig, transit);
  }

  await refresh();
  setInterval(refresh, 5000);
});
