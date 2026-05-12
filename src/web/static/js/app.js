/* ITL Attestation Dashboard — Client Logic
   All API calls use relative URLs; no hard-coded host.
*/

"use strict";

// ─────────────────────────────────────────────────────────────────────────────
// Toast
// ─────────────────────────────────────────────────────────────────────────────
function toast(msg, type) {
  const host = document.getElementById("f-toast-host");
  if (!host) return;

  const colours = {
    success: "#54b054",
    error:   "#ec7575",
    warning: "#f7cf6b",
    info:    "#479ef5",
  };
  const t = document.createElement("div");
  t.className = "f-toast";
  t.style.borderLeft = "3px solid " + (colours[type] || colours.info);
  t.textContent = msg;
  host.appendChild(t);

  setTimeout(() => {
    t.style.opacity = "0";
    setTimeout(() => t.remove(), 350);
  }, 3500);
}

// ─────────────────────────────────────────────────────────────────────────────
// Machines list — client-side filtering
// ─────────────────────────────────────────────────────────────────────────────
let _activeStatus = "";

function setStatusFilter(btn, status) {
  _activeStatus = status;
  document.querySelectorAll(".f-pivot-tab").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  applyFilter();
}

function applyFilter() {
  const q = (document.getElementById("f-search") ? document.getElementById("f-search").value : "").toLowerCase();
  let visible = 0;

  document.querySelectorAll(".machine-row").forEach(row => {
    const rowStatus = (row.dataset.status || "").toLowerCase();
    const rowText   = row.textContent.toLowerCase();

    const matchStatus = !_activeStatus || rowStatus === _activeStatus;
    const matchQuery  = !q || rowText.includes(q);

    if (matchStatus && matchQuery) {
      row.classList.remove("hidden");
      visible++;
    } else {
      row.classList.add("hidden");
    }
  });

  const cnt = document.getElementById("f-result-count");
  if (cnt) cnt.textContent = visible + " machine" + (visible !== 1 ? "s" : "");
}

// ─────────────────────────────────────────────────────────────────────────────
// Slide-in detail panel
// ─────────────────────────────────────────────────────────────────────────────
function openPanel(machineId) {
  const panel   = document.getElementById("f-panel");
  const overlay = document.getElementById("f-overlay");
  if (!panel) return;

  // Loading state
  const body = panel.querySelector(".f-panel-body");
  if (body) body.innerHTML = '<div style="padding:32px;text-align:center;color:rgba(255,255,255,.4);font-size:13px;">Loading…</div>';

  panel.classList.add("open");
  if (overlay) { overlay.style.display = "block"; }

  fetch("/api/machines/" + encodeURIComponent(machineId))
    .then(r => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(m => renderPanelContent(m))
    .catch(err => {
      if (body) body.innerHTML = '<div style="padding:32px;text-align:center;color:#ec7575;font-size:13px;">Failed to load machine details.</div>';
      console.error(err);
    });
}

function closePanel() {
  const panel   = document.getElementById("f-panel");
  const overlay = document.getElementById("f-overlay");
  if (panel)   panel.classList.remove("open");
  if (overlay) overlay.style.display = "none";
}

function renderPanelContent(m) {
  const panel = document.getElementById("f-panel");
  if (!panel) return;

  const header = panel.querySelector(".f-panel-header");
  if (header) {
    header.innerHTML = `
      <div>
        <div class="f-panel-title">${esc(m.hostname || m.id)}</div>
        <div class="f-panel-sub">${esc(m.id)}</div>
      </div>
      <button class="f-icon-btn" onclick="closePanel()" title="Close">
        <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
          <path d="M2.146 2.854a.5.5 0 1 1 .708-.708L8 7.293l5.146-5.147a.5.5 0 0 1 .708.708L8.707 8l5.147 5.146a.5.5 0 0 1-.708.708L8 8.707l-5.146 5.147a.5.5 0 0 1-.708-.708L7.293 8z"/>
        </svg>
      </button>`;
  }

  const statusClass = {
    attested:         "f-badge-success",
    registered:       "f-badge-info",
    pending_approval: "f-badge-warning",
    locked:           "f-badge-warning",
    revoked:          "f-badge-danger",
    rejected:         "f-badge-muted",
  };

  const roleName = {
    controlplane:  "Control Plane",
    "worker-infra": "Worker Infra",
    "worker-app":   "Worker App",
  };

  const body = panel.querySelector(".f-panel-body");
  if (!body) return;

  const actions = buildPanelActions(m);

  body.innerHTML = `
    <div class="f-panel-section">
      <div class="f-panel-section-title">Status &amp; Identity</div>
      <div class="f-detail-grid">
        <div class="f-detail-row"><div class="dk">Status</div><div class="dv"><span class="f-badge ${statusClass[m.status] || 'f-badge-muted'}"><span class="f-badge-dot"></span>${esc(m.status)}</span></div></div>
        <div class="f-detail-row"><div class="dk">Role</div><div class="dv"><span class="f-role-badge">${esc(roleName[m.role] || m.role)}</span></div></div>
        <div class="f-detail-row"><div class="dk">Hostname</div><div class="dv">${esc(m.hostname || '—')}</div></div>
        <div class="f-detail-row"><div class="dk">Cluster</div><div class="dv">${esc(m.cluster || '—')}</div></div>
        <div class="f-detail-row"><div class="dk">Namespace</div><div class="dv">${esc(m.namespace || '—')}</div></div>
      </div>
    </div>
    <div class="f-panel-section">
      <div class="f-panel-section-title">Hardware</div>
      <div class="f-detail-grid">
        <div class="f-detail-row"><div class="dk">Manufacturer</div><div class="dv">${esc(m.hw_manufacturer || '—')}</div></div>
        <div class="f-detail-row"><div class="dk">Model</div><div class="dv">${esc(m.hw_model || '—')}</div></div>
        <div class="f-detail-row"><div class="dk">Serial</div><div class="dv" style="font-family:var(--f-font-mono);font-size:11px">${esc(m.hw_serial || '—')}</div></div>
      </div>
    </div>
    <div class="f-panel-section">
      <div class="f-panel-section-title">Security Anchors</div>
      <div class="f-detail-grid">
        <div class="f-detail-row"><div class="dk">EK Cert</div><div class="dv" style="font-family:var(--f-font-mono);font-size:11px;word-break:break-all">${esc(m.ek_cert || '—')}</div></div>
        <div class="f-detail-row"><div class="dk">TPM Version</div><div class="dv">${esc(m.tpm_version || '—')}</div></div>
      </div>
    </div>
    <div class="f-panel-section">
      <div class="f-panel-section-title">Timeline</div>
      <div class="f-detail-grid">
        <div class="f-detail-row"><div class="dk">Registered</div><div class="dv">${fmtTs(m.registered_at)}</div></div>
        <div class="f-detail-row"><div class="dk">Last Attested</div><div class="dv">${fmtTs(m.last_attested_at)}</div></div>
        <div class="f-detail-row"><div class="dk">Status Changed</div><div class="dv">${fmtTs(m.status_changed_at)}</div></div>
        <div class="f-detail-row"><div class="dk">Created By</div><div class="dv">${esc(m.created_by || '—')}</div></div>
      </div>
    </div>
    <div class="f-panel-actions">${actions}</div>`;
}

function buildPanelActions(m) {
  const s = m.status;
  let html = "";
  if (s === "pending_approval" || s === "registered") {
    html += `<button class="f-btn f-btn-primary" onclick="machineAction('approve','${esc(m.id)}')">Approve</button>`;
  }
  if (s === "registered" || s === "attested") {
    html += `<button class="f-btn f-btn-secondary" onclick="machineAction('lock','${esc(m.id)}')">Lock</button>`;
  }
  if (s === "locked") {
    html += `<button class="f-btn f-btn-secondary" onclick="machineAction('unlock','${esc(m.id)}')">Unlock</button>`;
  }
  if (["pending_approval","registered","attested","locked"].includes(s)) {
    html += `<button class="f-btn f-btn-danger" onclick="machineAction('revoke','${esc(m.id)}')">Revoke</button>`;
  }
  if (!html) {
    html = `<span style="font-size:12px;color:rgba(255,255,255,.4)">No actions available for current status.</span>`;
  }
  return html;
}

// ─────────────────────────────────────────────────────────────────────────────
// Machine actions (POST)
// ─────────────────────────────────────────────────────────────────────────────
function machineAction(action, machineId) {
  fetch("/api/machines/" + encodeURIComponent(machineId) + "/" + action, { method: "POST" })
    .then(r => {
      if (!r.ok) return r.json().then(d => { throw new Error(d.error || "HTTP " + r.status); });
      return r.json();
    })
    .then(updated => {
      toast("Machine " + action + "d successfully.", "success");

      // Update the row badge inline if on machines list
      const row = document.querySelector('.machine-row[data-id="' + machineId + '"]');
      if (row) {
        row.dataset.status = updated.status;
        const badgeCell = row.querySelector(".status-cell");
        if (badgeCell) badgeCell.innerHTML = buildStatusBadge(updated.status);
      }

      // Re-render panel with updated data
      renderPanelContent(updated);
    })
    .catch(err => toast(err.message, "error"));
}

function buildStatusBadge(status) {
  const cls = {
    attested:         "f-badge-success",
    registered:       "f-badge-info",
    pending_approval: "f-badge-warning",
    locked:           "f-badge-warning",
    revoked:          "f-badge-danger",
    rejected:         "f-badge-muted",
  };
  return `<span class="f-badge ${cls[status] || 'f-badge-muted'}"><span class="f-badge-dot"></span>${status}</span>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Utility
// ─────────────────────────────────────────────────────────────────────────────
function esc(s) {
  if (!s) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#x27;");
}

function fmtTs(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

// ─────────────────────────────────────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  const search = document.getElementById("f-search");
  if (search) search.addEventListener("input", applyFilter);

  // Close panel when overlay clicked
  const overlay = document.getElementById("f-overlay");
  if (overlay) overlay.addEventListener("click", closePanel);

  // Keyboard: Escape closes panel
  document.addEventListener("keydown", e => { if (e.key === "Escape") closePanel(); });

  // Set first pivot tab active if on machines page
  const firstTab = document.querySelector(".f-pivot-tab");
  if (firstTab) firstTab.classList.add("active");
});
