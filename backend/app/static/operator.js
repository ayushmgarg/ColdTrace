/* operator.js — field view logic */

const ACTIONS = [
  { icon: "🌡️", text: "Check cold box temperature before handling any batch. Safe range: 2–8 °C." },
  { icon: "🔋", text: "If battery alarm is active, replace LTAT battery before dispatch." },
  { icon: "🚨", text: "If a temperature excursion is open, isolate the affected batch immediately and notify your supervisor." },
  { icon: "📋", text: "Log any manual observation in the incident comment trail via the dashboard." },
  { icon: "✅", text: "Confirm GPS is active on CCVE (vehicle device) before transit starts." },
];

document.addEventListener("DOMContentLoaded", async () => {
  requireSession();
  document.getElementById("logout-btn").addEventListener("click", logout);
  document.getElementById("go-dashboard").addEventListener("click", () => window.location.href = "/");

  // Static action checklist (no API needed)
  document.getElementById("op-actions").innerHTML = ACTIONS.map(a => `
    <div class="action-item">
      <span class="action-icon">${a.icon}</span>
      <span class="action-text">${a.text}</span>
    </div>
  `).join("");

  async function refresh() {
    const [me, overview, telemetry, incidents, gateways] = await Promise.all([
      fetchJson("/api/auth/me"),
      fetchJson("/api/overview"),
      fetchJson("/api/telemetry/recent?limit=8"),
      fetchJson("/api/incidents?limit=6"),
      fetchJson("/api/gateways"),
    ]);
    if (!me) return;

    // Identity
    document.getElementById("op-name").textContent = me.full_name;
    document.getElementById("op-role").textContent = `${me.role} · ${me.email}`;
    document.getElementById("op-open-incidents").textContent = overview.summary.open_incidents;
    const facCode = me.assigned_facility_id || "All";
    document.getElementById("op-facility").textContent = facCode.replace("FAC-","").replace("-"," ");

    // Telemetry reading cards
    const tel = telemetry || [];
    document.getElementById("op-telemetry").innerHTML = tel.length
      ? tel.map(t => {
          const tone = tempTone(t.temperature_c, t.min_temp_c, t.max_temp_c);
          const bat  = batteryTone(t.battery_voltage);
          return `
            <div class="reading-card ${tone === "critical" ? "critical" : tone === "warning" ? "warning" : ""}">
              <div class="reading-card-header">
                <span class="reading-device">${t.device_id}</span>
                <span class="reading-time">${formatTime(t.recorded_at)}</span>
              </div>
              <div class="reading-temps">
                <div>
                  <div class="reading-temp-val" style="color:var(--${tone === "healthy" ? "healthy" : tone === "warning" ? "warning" : "critical"})">${formatTemp(t.temperature_c)}</div>
                  <div class="reading-temp-lbl">Temperature</div>
                </div>
                <div>
                  <div class="reading-temp-val" style="font-size:1.1rem;color:var(--muted)">${t.humidity_pct != null ? t.humidity_pct.toFixed(0)+"%" : "—"}</div>
                  <div class="reading-temp-lbl">Humidity</div>
                </div>
                <div>
                  <div class="reading-temp-val" style="font-size:1.1rem;color:var(--${bat})">${t.battery_voltage != null ? t.battery_voltage.toFixed(2)+" V" : "—"}</div>
                  <div class="reading-temp-lbl">Battery</div>
                </div>
              </div>
              <div class="reading-meta">
                <span class="chip ${tone}">${tone}</span>
                <span class="chip neutral">${t.transport_mode.replace(/_/g," ")}</span>
                <span class="chip neutral">${(t.facility_name || t.facility_id || "").replace("FAC-","")}</span>
              </div>
            </div>
          `;
        }).join("")
      : `<p class="empty-state">No telemetry yet — start the simulator.</p>`;

    // Incidents
    const inc = incidents || [];
    document.getElementById("op-incidents").innerHTML = inc.length
      ? inc.map(i => `
          <div class="data-row" style="${i.severity === "critical" ? "border-color:rgba(248,113,113,.25)" : ""}">
            <div class="data-row-left">
              <div class="row-title">${i.incident_type.replace(/_/g," ")}</div>
              <div class="row-sub">${i.reason}</div>
              <div class="ts">${i.device_id} · ${i.facility_name}</div>
            </div>
            <div class="data-row-right">
              <span class="chip ${i.severity}">${i.severity}</span>
              <span class="chip ${i.status === "open" ? "critical" : "healthy"}">${i.status}</span>
            </div>
          </div>
        `).join("")
      : `<p class="empty-state">No active incidents in your scope. 🎉</p>`;

    // Gateway buffer status (DC: store-and-forward)
    const gws = gateways || [];
    document.getElementById("op-gateways").innerHTML = gws.length
      ? gws.map(g => {
          const dot = g.status === "online" ? "healthy" : g.status === "degraded" ? "warning" : "offline";
          return `
            <div class="data-row" style="margin-bottom:.5rem">
              <div class="data-row-left">
                <div class="row-title" style="display:flex;align-items:center;gap:.5rem">
                  <span class="status-dot ${dot}"></span> ${g.id}
                </div>
                <div class="row-sub">${g.facility_name} · FW ${g.firmware_version}</div>
              </div>
              <div class="data-row-right">
                <span class="chip ${g.status === "online" ? "online" : "degraded"}">${g.status}</span>
                ${g.buffered_packets > 0
                  ? `<span class="chip warning">${g.buffered_packets} buffered</span>`
                  : `<span class="ts" style="color:var(--healthy)">✓ synced</span>`}
              </div>
            </div>
          `;
        }).join("")
      : `<p class="empty-state">No gateway data.</p>`;
  }

  await refresh();
  setInterval(refresh, 5000);
});
