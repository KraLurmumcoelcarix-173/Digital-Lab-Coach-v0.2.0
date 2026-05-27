/* DLC front end. Loads Cytoscape, handles file uploads,
   renders the signal-flow graph, drives the summary and hover panels.
*/

cytoscape.use(window.cytoscapeDagre);

const FAMILY_COLORS = {
  "io-in":     "#cfe5ff",
  "io-out":    "#ffdcb3",
  "gate":      "#b9e4c1",
  "arith":     "#f4b9b9",
  "mux":       "#d8c4ef",
  "splitter":  "#f1ea9a",
  "storage":   "#d3d3d3",
  "tunnel":    "#f7d7e8",
  "subcircuit":"#ffc1c1",
  "const":     "#dfdfdf",
  "clock":     "#dfdfdf",
  "other":     "#e9ecef",
};

const CY_STYLE = [
  {
    selector: "node",
    style: {
      "shape": "round-rectangle",
      "background-color": (n) => FAMILY_COLORS[n.data("family")] || "#e9ecef",
      "border-color": "#444",
      "border-width": 1,
      "label": "data(label)",
      "color": "#1f2933",
      "font-size": 10,
      "text-wrap": "wrap",
      "text-max-width": 90,
      "text-valign": "center",
      "text-halign": "center",
      "width": 70,
      "height": 38,
      "padding": "4px",
    },
  },
  {
    selector: "node:selected",
    style: {
      "border-color": "#2563eb",
      "border-width": 3,
    },
  },
  {
    selector: "node.faded",
    style: {
      "opacity": 0.22,
    },
  },
  {
    selector: "edge",
    style: {
      "width": 1.5,
      "line-color": "#9aa1ab",
      "target-arrow-color": "#9aa1ab",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      "arrow-scale": 0.9,
    },
  },
  {
    selector: "edge.faded",
    style: { "opacity": 0.1 },
  },
  {
    selector: "edge.highlight",
    style: {
      "line-color": "#2563eb",
      "target-arrow-color": "#2563eb",
      "width": 2.5,
    },
  },
];

// DOM 

const fileInput   = document.getElementById("file-input");
const filenameEl  = document.getElementById("filename");
const placeholder = document.getElementById("placeholder");
const summaryEl   = document.getElementById("summary");
const hoverEl     = document.getElementById("hover-info");

let cy = null;

// Upload

fileInput.addEventListener("change", async () => {
  const file = fileInput.files[0];
  if (!file) return;
  filenameEl.textContent = file.name;
  await uploadCircuit(file);
});

async function uploadCircuit(file) {
  const fd = new FormData();
  fd.append("file", file);

  summaryEl.innerHTML = `<span class="muted">Parsing ${escapeHtml(file.name)}...</span>`;

  let res;
  try {
    res = await fetch("/api/circuit", { method: "POST", body: fd });
  } catch (err) {
    summaryEl.textContent = "Upload failed: " + err;
    return;
  }
  if (!res.ok) {
    const text = await res.text();
    summaryEl.innerHTML = `<span style="color:#991b1b">${escapeHtml(text)}</span>`;
    return;
  }
  const data = await res.json();
  renderGraph(data.graph);
  renderSummary(data.summary);
}

// Graph rendering 

function renderGraph(graph) {
  placeholder.classList.add("hidden");

  if (cy) cy.destroy();

  cy = cytoscape({
    container: document.getElementById("cy"),
    elements: {
      nodes: graph.nodes,
      edges: graph.edges,
    },
    style: CY_STYLE,
    layout: {
      name: "dagre",
      rankDir: "LR",
      nodeSep: 30,
      rankSep: 60,
      edgeSep: 10,
      animate: false,
    },
    wheelSensitivity: 0.2,
    minZoom: 0.15,
    maxZoom: 3,
  });

  cy.on("mouseover", "node", (evt) => {
    const node = evt.target;
    cy.elements().addClass("faded");
    const nb = node.closedNeighborhood();
    nb.removeClass("faded");
    nb.edges().addClass("highlight");
    renderHoverNode(node);
  });
  cy.on("mouseout", "node", () => {
    cy.elements().removeClass("faded");
    cy.edges().removeClass("highlight");
  });

  cy.on("mouseover", "edge", (evt) => {
    renderHoverEdge(evt.target);
  });
  cy.on("mouseout", "edge", () => {
  });
}

function renderHoverNode(node) {
  const d = node.data();
  const attrRows = Object.entries(d.attributes || {})
    .filter(([k]) => k !== "Label")
    .map(([k, v]) =>
      `<tr><td class="k">${escapeHtml(k)}</td><td class="v">${escapeHtml(String(v))}</td></tr>`
    ).join("");
  hoverEl.innerHTML = `
    <table>
      <tr><td class="k">type</td><td class="v">${escapeHtml(d.element_name)}</td></tr>
      <tr><td class="k">label</td><td class="v">${escapeHtml(d.comp_label || "(none)")}</td></tr>
      <tr><td class="k">index</td><td class="v">${escapeHtml(d.id)}</td></tr>
      <tr><td class="k">family</td><td class="v">${escapeHtml(d.family)}</td></tr>
      <tr><td class="k">.dig pos</td><td class="v">(${d.x_dig}, ${d.y_dig})</td></tr>
      ${attrRows}
    </table>
  `;
}

function renderHoverEdge(edge) {
  const d = edge.data();
  hoverEl.innerHTML = `
    <table>
      <tr><td class="k">net</td><td class="v">${escapeHtml(d.net_id ?? "?")}</td></tr>
      <tr><td class="k">from</td><td class="v">${escapeHtml(d.source)}.${escapeHtml(d.driver_pin || "?")}</td></tr>
      <tr><td class="k">to</td><td class="v">${escapeHtml(d.target)}.${escapeHtml(d.sink_pin || "?")}</td></tr>
    </table>
  `;
}

// Summary panel 

function renderSummary(s) {
  const stats = s.net_stats || {};
  const undrivenBadge = stats.undriven_with_pins
    ? `<span class="badge warn">${stats.undriven_with_pins} undriven</span>`
    : "";
  const multiBadge = stats.multi_driver
    ? `<span class="badge err">${stats.multi_driver} multi-driver</span>`
    : "";

  const inventoryRows = Object.entries(s.inventory || {})
    .sort(([, a], [, b]) => b - a)
    .map(([name, count]) =>
      `<tr><td class="k">${escapeHtml(name)}</td><td class="v">${count}</td></tr>`
    ).join("");

  const inputsList = (s.inputs || [])
    .map((p) => `<li>${escapeHtml(p.label)} <span class="muted">${p.bits} bit${p.bits === 1 ? "" : "s"}</span></li>`)
    .join("");
  const outputsList = (s.outputs || [])
    .map((p) => `<li>${escapeHtml(p.label)} <span class="muted">${p.bits} bit${p.bits === 1 ? "" : "s"}</span></li>`)
    .join("");
  const subsList = (s.subcircuits || [])
    .map((sub) => {
      const badge = sub.resolved
        ? ""
        : `<span class="badge err">missing</span>`;
      return `<li>${escapeHtml(sub.reference)} ${badge}</li>`;
    })
    .join("");

  summaryEl.innerHTML = `
    <table>
      <tr><td class="k">nets</td><td class="v">${stats.total ?? 0}</td></tr>
      <tr><td class="k">driven</td><td class="v">${stats.driven ?? 0}</td></tr>
      <tr><td class="k">issues</td><td class="v">${undrivenBadge}${multiBadge}${(!undrivenBadge && !multiBadge) ? '<span class="muted">none</span>' : ""}</td></tr>
    </table>

    <h2 style="margin-top:14px">Inputs (${(s.inputs || []).length})</h2>
    ${inputsList ? `<ul>${inputsList}</ul>` : `<div class="muted">(none)</div>`}

    <h2>Outputs (${(s.outputs || []).length})</h2>
    ${outputsList ? `<ul>${outputsList}</ul>` : `<div class="muted">(none)</div>`}

    <h2>Subcircuits (${(s.subcircuits || []).length})</h2>
    ${subsList ? `<ul>${subsList}</ul>` : `<div class="muted">(none)</div>`}

    <h2>Inventory</h2>
    <table>${inventoryRows || '<tr><td class="muted">(empty)</td></tr>'}</table>
  `;
}

// Utility 

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}