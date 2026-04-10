document.addEventListener("DOMContentLoaded", async () => {
  requireSession();
  document.getElementById("logout-btn").addEventListener("click", logout);
  document.getElementById("go-dashboard").addEventListener("click", () => {
    window.location.href = "/";
  });

  async function refresh() {
    const [me, overview, telemetry, incidents] = await Promise.all([
      fetchJson("/api/auth/me"),
      fetchJson("/api/overview"),
      fetchJson("/api/telemetry/recent?limit=6"),
      fetchJson("/api/incidents?limit=6"),
    ]);

    document.getElementById("operator-name").textContent = me.full_name;
    document.getElementById("operator-role").textContent = `${me.role} · ${me.email}`;
    document.getElementById("operator-facility").textContent = me.assigned_facility_id || "Global access";
    document.getElementById("operator-open-incidents").textContent = overview.summary.open_incidents;

    const actions = [
      "Check current cold box temperature before handling a batch.",
      "If excursion persists, isolate the affected batch and alert supervisor.",
      "Verify battery condition on field carriers before dispatch.",
      "Use the incident list below as your immediate action queue.",
    ];
    document.getElementById("operator-actions").innerHTML = actions.map((item) => `
      <div class="list-card">
        <strong>${item}</strong>
      </div>
    `).join("");

    document.getElementById("operator-telemetry").innerHTML = telemetry.map((item) => `
      <div class="list-card">
        <div>
          <strong>${item.device_id}</strong>
          <p>${formatTemp(item.temperature_c)} · ${item.humidity_pct.toFixed(1)}%</p>
        </div>
        <div class="right-col">
          <span class="chip ${chipToneForTemperature(item.temperature_c, item.min_temp_c, item.max_temp_c)}">${item.transport_mode}</span>
          <span class="subtle">${formatTime(item.recorded_at)}</span>
        </div>
      </div>
    `).join("");

    document.getElementById("operator-incidents").innerHTML = incidents.length
      ? incidents.map((item) => `
          <div class="list-card">
            <div>
              <strong>${item.incident_type.replaceAll("_", " ")}</strong>
              <p>${item.reason}</p>
            </div>
            <span class="chip ${item.severity}">${item.severity}</span>
          </div>
        `).join("")
      : `<p class="empty-state">No active incidents in your current scope.</p>`;
  }

  await refresh();
  setInterval(refresh, 5000);
});

