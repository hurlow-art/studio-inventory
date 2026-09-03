#!/usr/bin/env python3
"""
generate_dashboard.py
---------------------
Reads the Master Hardware Tracker Google Sheet (both the 'Master Parts'
and 'Projects' tabs) and generates a self-contained index.html dashboard.

Run by GitHub Actions — requires GOOGLE_CREDENTIALS_JSON and
SPREADSHEET_ID environment variables (set as GitHub Secrets).

Usage:
    python scripts/generate_dashboard.py
"""

import json
import os
import re
import sys

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ── Config ───────────────────────────────────────────────────────
SPREADSHEET_ID   = os.environ.get("SPREADSHEET_ID", "1iw1wAeciuNL9R7y-18p9xG2OUMtdDt8X")
CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")
OUTPUT_PATH      = "index.html"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Installation full names
INSTALL_NAMES = {
    "PHO":  "Call Dad",
    "PHI":  "Philco",
    "DRV":  "Passion Pit",
    "QRK":  "Quarks",
    "MDV":  "Morning Doves",
    "TYP":  "It\u2019s Hard to Say",
    "DRK":  "Hello Darkness",
    "CLO":  "Cloche",
    "MKY":  "Mickey",
    "R40":  "Radio 40s",
    "DCT":  "Dictaphone",
    "THR":  "Thermostat",
    "RRL":  "Reel-to-Reel",
    "CSH":  "Cash Register",
    "S8":   "Super 8",
    "VNT":  "Ventilator",
    "CLK":  "Clock",
    "ANS":  "Answering Machine",
    "PHO2": "Phone 2",
}

STATE_COLORS = {
    "Planning":       "#F0F0F0",
    "Parts sourcing": "#FFF3CD",
    "Building":       "#DBEAFE",
    "Built":          "#dff0df",
    "Exhibited":      "#E8D5F5",
    "On hold":        "#EBEBEB",
}

# Cell fill colors that indicate assignment status
# These are the hex values used in the spreadsheet
GREEN  = "FFC8E6C9"   # In Hand
YELLOW = "FFFFF3CD"   # To Order
GRAY   = "FFB0BEC5"   # Build complete (PHO column)


# ── Google Sheets connection ─────────────────────────────────────

def get_service():
    if not CREDENTIALS_JSON:
        print("ERROR: GOOGLE_CREDENTIALS_JSON environment variable not set.")
        sys.exit(1)
    creds_data = json.loads(CREDENTIALS_JSON)
    creds = Credentials.from_service_account_info(creds_data, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


# ── Read Projects tab ────────────────────────────────────────────

def read_build_states(service):
    """Read the Projects tab and return {code: build_state}."""
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="Projects!A2:C100"
    ).execute()
    rows = result.get("values", [])
    states = {}
    for row in rows:
        if len(row) >= 3 and row[0] and row[2]:
            code  = row[0].strip()
            state = row[2].strip()
            # Skip the legend rows at the bottom
            if code not in ("Build State options:", "Planning", "Parts sourcing",
                            "Building", "Built", "Exhibited", "On hold"):
                states[code] = state
    return states


# ── Read Master Parts tab ────────────────────────────────────────

def read_parts(service):
    """
    Read Master Parts tab. Returns a list of dicts representing rows,
    plus the list of installation column codes in order.
    """
    # Get values
    values_result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="Master Parts!A1:AD200"
    ).execute()
    values = values_result.get("values", [])

    # Get cell metadata for fill colors
    fields = "sheets(data(rowData(values(effectiveFormat/backgroundColor,effectiveValue))))"
    meta_result = service.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID,
        ranges=["Master Parts!A1:AD200"],
        fields=fields
    ).execute()

    sheet_data = meta_result["sheets"][0]["data"][0]["rowData"]

    # Find header row (row index 3, 0-based)
    # Row 4 in sheet = index 3: has PHO, PHI, DRV etc.
    header_row_idx = 3
    header_values = values[header_row_idx] if len(values) > header_row_idx else []

    # Find install columns (cols with 3-4 char codes after col F)
    install_cols = {}  # col_index -> code
    for i, val in enumerate(header_values):
        if i >= 6 and val and len(val.strip()) <= 5 and val.strip().isupper():
            install_cols[i] = val.strip()

    print(f"Install columns found: {install_cols}")

    # Parse data rows (row 5 onwards = index 4+)
    items = []
    for row_idx in range(4, len(values)):
        row_vals  = values[row_idx]
        row_meta  = sheet_data[row_idx] if row_idx < len(sheet_data) else {}
        meta_vals = row_meta.get("values", [])

        if not row_vals:
            continue

        num  = row_vals[0].strip() if len(row_vals) > 0 else ""
        comp = row_vals[1].strip() if len(row_vals) > 1 else ""

        if not comp:
            continue

        # ESTIMATED TOTAL row — stop
        if "ESTIMATED TOTAL" in comp:
            break

        # Section header rows (col A empty, col B starts with spaces)
        if not num and comp:
            items.append({"type": "section", "label": comp.strip()})
            continue

        # Skip non-numeric item rows
        try:
            int(num)
        except ValueError:
            continue

        cat    = row_vals[2].strip()  if len(row_vals) > 2 else ""
        source = row_vals[3].strip()  if len(row_vals) > 3 else ""
        price  = row_vals[4].strip()  if len(row_vals) > 4 else ""
        notes  = row_vals[25].strip() if len(row_vals) > 25 else ""

        # Parse quantity from component name
        qty, qty_unit = parse_qty(comp)

        # Parse assignments from install columns
        assignments = {}
        for col_idx, code in install_cols.items():
            val = row_vals[col_idx].strip() if col_idx < len(row_vals) else ""
            if val and val != "0":
                # Get fill color
                cell_meta = meta_vals[col_idx] if col_idx < len(meta_vals) else {}
                bg = cell_meta.get("effectiveFormat", {}).get("backgroundColor", {})
                fill_hex = rgb_to_hex(bg)
                status = color_to_status(fill_hex)
                assignments[code] = status

        items.append({
            "type":        "item",
            "num":         int(num),
            "component":   comp,
            "category":    cat,
            "source":      source,
            "price":       price,
            "qty":         qty,
            "qty_unit":    qty_unit,
            "assignments": assignments,
            "notes":       notes,
        })

    return items, list(install_cols.values())


# ── Helpers ──────────────────────────────────────────────────────

def rgb_to_hex(bg):
    """Convert Google Sheets RGB dict (0–1 floats) to hex string."""
    r = int(round(bg.get("red",   1) * 255))
    g = int(round(bg.get("green", 1) * 255))
    b = int(round(bg.get("blue",  1) * 255))
    return f"FF{r:02X}{g:02X}{b:02X}"


def color_to_status(hex_color):
    """Map a fill hex color to a status string."""
    # Tolerance matching — colors may vary slightly
    r = int(hex_color[2:4], 16)
    g = int(hex_color[4:6], 16)
    b = int(hex_color[6:8], 16)

    # Green: C8E6C9 ≈ (200, 230, 201)
    if r < 220 and g > 200 and b < 220 and g > r:
        return "in_hand"
    # Yellow: FFF3CD ≈ (255, 243, 205)
    if r > 240 and g > 220 and b < 220:
        return "to_order"
    # Gray: B0BEC5 ≈ (176, 190, 197) — completed build
    if 150 < r < 210 and 170 < g < 210 and 180 < b < 220:
        return "complete"
    # Default — has a value but color unrecognized
    return "in_hand"


QTY_OVERRIDES = {
    1: (7, "units"), 4: (7, "units"), 7: (7, "units"),
    8: (3, "units"), 14: (4, "units"), 15: (3, "units"),
    20: (2, "pack"), 26: (5, "pack"), 27: (25, "pack"),
    30: (120, "pc"), 42: (5, "units"), 45: (2, "units"),
    53: (30, "pc"), 54: (10, "pc"), 56: (3, "units"),
    57: (2, "units"), 59: (3, "pc"), 63: (6, "pc"),
    65: (15, "pc"), 85: (50, "pc"),
}


def parse_qty(name, num=None):
    if num and num in QTY_OVERRIDES:
        return QTY_OVERRIDES[num]
    patterns = [
        r"(\d+)\s*-?\s*pack", r"(\d+)\s*pc\b", r"(\d+)\s*pcs\b",
        r"(\d+)\s*units?\b", r"\xd7\s*(\d+)", r"\u2014\s*(\d+)\s*units",
    ]
    for p in patterns:
        m = re.search(p, name, re.IGNORECASE)
        if m:
            return int(m.group(1)), "pc"
    return 1, "unit"


# ── HTML generation ──────────────────────────────────────────────

def build_html(items, build_states):
    data_json         = json.dumps({"items": items, "install_names": INSTALL_NAMES})
    build_states_json = json.dumps(build_states)
    state_colors_json = json.dumps(STATE_COLORS)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Studio Inventory — Jeff Hurlow</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;1,400;1,500&display=swap');
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --ink: #1a1a18; --ink-mid: #5a5a52; --ink-light: #9a9a8e;
    --rule: #d8d4cc; --green: #7aad7a; --yellow: #c8a84b;
    --gray: #9aacb2; --tag-bg: #eceae4;
  }}
  html, body {{ background: transparent; }}
  body {{ font-family: 'EB Garamond', Georgia, serif; font-size: 18px;
    line-height: 1.65; color: var(--ink); padding: 0 0 120px; }}
  .view-toggle {{ padding: 44px 60px 0; display: flex; gap: 28px;
    border-bottom: 1px solid var(--rule); padding-bottom: 0; }}
  .view-tab {{ font-family: 'EB Garamond', Georgia, serif; font-size: 17px;
    color: var(--ink-light); background: transparent; border: none;
    border-bottom: 2px solid transparent; padding: 0 0 14px; cursor: pointer;
    font-style: italic; transition: color 0.15s; margin-bottom: -1px; }}
  .view-tab:hover {{ color: var(--ink); }}
  .view-tab.active {{ color: var(--ink); border-bottom-color: var(--ink); font-style: normal; }}
  .controls {{ padding: 40px 60px 0; display: flex; gap: 24px; align-items: center; flex-wrap: wrap; }}
  .search-wrap {{ flex: 1; min-width: 240px; }}
  input[type="text"] {{ width: 100%; font-family: 'EB Garamond', Georgia, serif;
    font-size: 18px; color: var(--ink); background: transparent; border: none;
    border-bottom: 1px solid var(--ink); padding: 6px 0; outline: none; }}
  input[type="text"]::placeholder {{ color: var(--ink-light); font-style: italic; }}
  .filter-group {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .filter-btn {{ font-family: 'EB Garamond', Georgia, serif; font-size: 15px;
    color: var(--ink-mid); background: transparent; border: 1px solid var(--rule);
    padding: 4px 12px; cursor: pointer; transition: all 0.15s; }}
  .filter-btn:hover {{ border-color: var(--ink-mid); color: var(--ink); }}
  .filter-btn.active {{ background: transparent; color: var(--ink);
    border-color: var(--ink); font-style: italic; }}
  .legend {{ padding: 20px 60px 0; display: flex; gap: 20px; font-size: 15px;
    color: var(--ink-light); font-style: italic; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .results-meta {{ padding: 28px 60px 0; font-size: 15px; color: var(--ink-light);
    font-style: italic; min-height: 28px; }}
  .table-wrap {{ padding: 20px 60px 0; }}
  table {{ width: 100%; border-collapse: collapse; }}
  thead th {{ font-family: 'EB Garamond', Georgia, serif; font-size: 14px;
    font-weight: 400; color: var(--ink-light); text-align: left;
    padding: 0 24px 10px 0; border-bottom: 1px solid var(--rule);
    white-space: nowrap; letter-spacing: 0.03em; }}
  tbody tr {{ border-bottom: 1px solid var(--rule); transition: background 0.1s; }}
  tbody tr:hover {{ background: rgba(0,0,0,0.025); }}
  tbody tr.hidden {{ display: none; }}
  tbody td {{ font-size: 16px; padding: 11px 0; vertical-align: top; color: var(--ink); }}
  .td-num {{ color: var(--ink-light); font-size: 13px; width: 32px; padding-top: 13px; }}
  .td-component {{ font-size: 17px; min-width: 200px; }}
  .td-component .component-name {{ display: block; }}
  .td-component .component-notes {{ display: block; font-size: 14px;
    color: var(--ink-light); font-style: italic; margin-top: 2px; line-height: 1.4; }}
  .td-cat {{ font-size: 15px; color: var(--ink-mid); white-space: nowrap; padding-right: 24px; }}
  .td-qty {{ font-size: 15px; color: var(--ink-mid); white-space: nowrap; padding-right: 24px; }}
  tr.section-row td {{ font-size: 12px; letter-spacing: 0.12em; color: var(--ink-light);
    text-transform: uppercase; padding: 28px 0 8px; border-bottom: none; }}
  tr.section-row:hover {{ background: transparent; }}
  .status-dot {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%;
    margin-right: 5px; vertical-align: middle; }}
  .dot-in_hand {{ background: var(--green); }}
  .dot-to_order {{ background: var(--yellow); }}
  .dot-complete {{ background: var(--gray); }}
  .empty-state {{ padding: 48px 60px; font-size: 15px; color: var(--ink-light); font-style: italic; }}
  .project-select-wrap {{ padding: 32px 60px 0; display: flex; align-items: baseline; gap: 16px; }}
  .project-label {{ font-size: 15px; color: var(--ink-mid); font-style: italic; white-space: nowrap; }}
  .project-pills {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .project-pill {{ font-family: 'EB Garamond', Georgia, serif; font-size: 15px;
    color: var(--ink-mid); background: transparent; border: 1px solid var(--rule);
    padding: 3px 11px; cursor: pointer; transition: all 0.15s; }}
  .project-pill:hover {{ border-color: var(--ink-mid); color: var(--ink); }}
  .project-pill.active {{ background: transparent; color: var(--ink);
    border-color: var(--ink); font-style: italic; }}
  .project-panel {{ display: none; padding: 32px 60px 0; }}
  .project-panel.visible {{ display: block; }}
  .project-panel-title {{ font-size: 22px; font-style: italic; margin-bottom: 4px; }}
  .project-panel-sub {{ font-size: 14px; color: var(--ink-light); margin-bottom: 28px;
    display: flex; align-items: center; gap: 12px; }}
  .build-state-badge {{ font-size: 12px; font-style: normal; color: var(--ink);
    padding: 2px 10px; border-radius: 2px; white-space: nowrap; }}
  .project-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0;
    border-top: 1px solid var(--rule); }}
  .project-item {{ padding: 14px 20px 14px 0; border-bottom: 1px solid var(--rule); }}
  .project-item-name {{ font-size: 16px; }}
  .project-item-meta {{ font-size: 13px; color: var(--ink-light); margin-top: 2px; font-style: italic; }}
  .project-item-status {{ font-size: 12px; margin-top: 5px; }}
  @media (max-width: 768px) {{
    .view-toggle, .controls, .project-select-wrap, .table-wrap,
    .results-meta, .legend, .project-panel {{ padding-left: 24px; padding-right: 24px; }}
    .project-grid {{ grid-template-columns: 1fr; }}
    .td-cat, .td-qty {{ display: none; }}
  }}
</style>
</head>
<body>

<div class="view-toggle">
  <button class="view-tab active" onclick="setView('inventory')">All parts</button>
  <button class="view-tab" onclick="setView('project')">By project</button>
</div>

<div id="inventory-view">
  <div class="controls">
    <div class="search-wrap">
      <input type="text" id="search" placeholder="Search components, categories, notes\u2026" oninput="filterTable()">
    </div>
    <div class="filter-group" id="cat-filters"></div>
  </div>
  <div class="legend">
    <span class="legend-item"><span class="status-dot dot-in_hand"></span>In hand</span>
    <span class="legend-item"><span class="status-dot dot-to_order"></span>To order</span>
    <span class="legend-item"><span class="status-dot dot-complete"></span>Build complete</span>
  </div>
  <div class="results-meta" id="results-meta"></div>
  <div class="table-wrap">
    <table id="parts-table">
      <thead>
        <tr>
          <th class="td-num">#</th>
          <th>Component</th>
          <th>Category</th>
          <th>Qty</th>
        </tr>
      </thead>
      <tbody id="table-body"></tbody>
    </table>
    <div class="empty-state" id="empty-state" style="display:none;">Nothing matches that search.</div>
  </div>
</div>

<div id="project-view" style="display:none;">
  <div class="project-select-wrap">
    <span class="project-label">Select a piece \u2014</span>
    <div class="project-pills" id="project-pills"></div>
  </div>
  <div class="project-panel" id="project-panel">
    <div class="project-panel-title" id="panel-title"></div>
    <div class="project-panel-sub" id="panel-sub"></div>
    <div class="project-grid" id="panel-grid"></div>
  </div>
</div>

<script>
const DATA = {data_json};
const INSTALL_NAMES = DATA.install_names;
const BUILD_STATES = {build_states_json};
const STATE_COLORS = {state_colors_json};
const ITEMS = DATA.items;

let activeCategory = 'All';

// Build category filters
const categories = ['All', ...new Set(ITEMS.filter(i=>i.type==='item').map(i=>i.category).filter(Boolean))].sort((a,b)=>a==='All'?-1:b==='All'?1:a.localeCompare(b));
const catFilters = document.getElementById('cat-filters');
categories.forEach(cat => {{
  const btn = document.createElement('button');
  btn.className = 'filter-btn' + (cat==='All'?' active':'');
  btn.textContent = cat;
  btn.onclick = () => {{
    activeCategory = cat;
    document.querySelectorAll('.filter-btn').forEach(b=>b.classList.toggle('active',b.textContent===cat));
    filterTable();
  }};
  catFilters.appendChild(btn);
}});

// Build project pills
const projects = [...new Set(ITEMS.filter(i=>i.type==='item').flatMap(i=>Object.keys(i.assignments)))].sort();
const pillsEl = document.getElementById('project-pills');
projects.forEach(code => {{
  const btn = document.createElement('button');
  btn.className = 'project-pill';
  btn.textContent = INSTALL_NAMES[code] ? `${{INSTALL_NAMES[code]}} (${{code}})` : code;
  btn.onclick = () => {{
    document.querySelectorAll('.project-pill').forEach(b=>b.classList.toggle('active',b===btn));
    showProjectPanel(code);
  }};
  pillsEl.appendChild(btn);
}});

// Build table
const tbody = document.getElementById('table-body');
ITEMS.forEach(item => {{
  const tr = document.createElement('tr');
  if (item.type === 'section') {{
    tr.className = 'section-row';
    tr.innerHTML = `<td colspan="4">${{item.label}}</td>`;
  }} else {{
    tr.dataset.component = item.component.toLowerCase();
    tr.dataset.category  = item.category;
    tr.dataset.notes     = item.notes.toLowerCase();
    const qtyStr = item.qty > 1 || item.qty_unit !== 'unit' ? `${{item.qty}}\u00a0${{item.qty_unit}}` : '1';
    tr.innerHTML = `
      <td class="td-num">${{item.num}}</td>
      <td class="td-component">
        <span class="component-name">${{item.component}}</span>
        ${{item.notes ? `<span class="component-notes">${{item.notes}}</span>` : ''}}
      </td>
      <td class="td-cat">${{item.category}}</td>
      <td class="td-qty">${{qtyStr}}</td>
    `;
  }}
  tbody.appendChild(tr);
}});

function filterTable() {{
  const q = document.getElementById('search').value.toLowerCase().trim();
  const rows = tbody.querySelectorAll('tr');
  let visible = 0; let lastSec = null; let lastSecVis = false;
  rows.forEach(tr => {{
    if (tr.classList.contains('section-row')) {{
      if (lastSec) lastSec.classList.toggle('hidden', !lastSecVis);
      lastSec = tr; lastSecVis = false; return;
    }}
    const matchQ = !q || tr.dataset.component.includes(q) || tr.dataset.notes.includes(q) || (tr.dataset.category||'').toLowerCase().includes(q);
    const matchC = activeCategory==='All' || tr.dataset.category===activeCategory;
    const show   = matchQ && matchC;
    tr.classList.toggle('hidden', !show);
    if (show) {{ visible++; lastSecVis = true; }}
  }});
  if (lastSec) lastSec.classList.toggle('hidden', !lastSecVis);
  const total = ITEMS.filter(i=>i.type==='item').length;
  document.getElementById('results-meta').textContent = (q || activeCategory!=='All') ? `${{visible}} of ${{total}} parts` : `${{total}} parts`;
  document.getElementById('empty-state').style.display = visible===0 ? 'block' : 'none';
}}

function showProjectPanel(code) {{
  const name     = INSTALL_NAMES[code] || code;
  const assigned = ITEMS.filter(i=>i.type==='item' && i.assignments[code]);
  const inHand   = assigned.filter(i=>i.assignments[code]==='in_hand'||i.assignments[code]==='complete');
  const toOrder  = assigned.filter(i=>i.assignments[code]==='to_order');
  const state    = BUILD_STATES[code] || 'Planning';
  const color    = STATE_COLORS[state] || '#F0F0F0';

  document.getElementById('panel-title').textContent = name;
  document.getElementById('panel-sub').innerHTML =
    `${{assigned.length}} parts \u2014 ${{inHand.length}} in hand, ${{toOrder.length}} to order
     <span class="build-state-badge" style="background:${{color}}">${{state}}</span>`;

  const grid = document.getElementById('panel-grid');
  grid.innerHTML = '';
  assigned.forEach(item => {{
    const status = item.assignments[code];
    const dotCls = status==='to_order' ? 'dot-to_order' : 'dot-in_hand';
    const label  = status==='to_order' ? 'To order' : 'In hand';
    const div    = document.createElement('div');
    div.className = 'project-item';
    div.innerHTML = `
      <div class="project-item-name">${{item.component}}</div>
      <div class="project-item-meta">${{item.category}}</div>
      <div class="project-item-status"><span class="status-dot ${{dotCls}}"></span>${{label}}</div>
    `;
    grid.appendChild(div);
  }});
  document.getElementById('project-panel').classList.add('visible');
}}

function setView(view) {{
  document.getElementById('inventory-view').style.display = view==='inventory'?'block':'none';
  document.getElementById('project-view').style.display   = view==='project'?'block':'none';
  document.querySelectorAll('.view-tab').forEach((t,i)=>t.classList.toggle('active',(i===0&&view==='inventory')||(i===1&&view==='project')));
}}

filterTable();
</script>
</body>
</html>"""


# ── Main ─────────────────────────────────────────────────────────

def main():
    print("Connecting to Google Sheets...")
    service = get_service()

    print("Reading build states from Projects tab...")
    build_states = read_build_states(service)
    print(f"  Found {len(build_states)} project states")

    print("Reading parts from Master Parts tab...")
    items, install_codes = read_parts(service)
    item_count = len([i for i in items if i["type"] == "item"])
    print(f"  Found {item_count} parts across {len(install_codes)} installations")

    print("Generating index.html...")
    html = build_html(items, build_states)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Done — wrote {len(html):,} chars to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
