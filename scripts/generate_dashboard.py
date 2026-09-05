#!/usr/bin/env python3
"""
generate_dashboard.py
---------------------
Reads the Master Hardware Tracker Google Sheet (three tabs: Inventory,
Allocations, Projects) and generates a self-contained index.html dashboard.

Run by GitHub Actions — requires GOOGLE_CREDENTIALS_JSON and
SPREADSHEET_ID environment variables (set as GitHub Secrets).
"""

import json
import os
import sys

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SPREADSHEET_ID   = os.environ.get("SPREADSHEET_ID", "1qGiPGU7ai-O_di_ADACI-grstCYAAkv4bUKt-ORLUEc")
CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")
OUTPUT_PATH      = "index.html"
SCOPES           = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

STATE_COLORS = {
    "Planning":       "#F0F0F0",
    "Parts sourcing": "#FFF3CD",
    "Building":       "#DBEAFE",
    "Built":          "#dff0df",
    "Exhibited":      "#E8D5F5",
    "On hold":        "#EBEBEB",
}

STATUS_COLORS = {
    "In use":    "#dff0df",
    "Reserved":  "#DBEAFE",
    "Available": "#F0F0F0",
}


def get_service():
    if not CREDENTIALS_JSON:
        print("ERROR: GOOGLE_CREDENTIALS_JSON not set.")
        sys.exit(1)
    creds = Credentials.from_service_account_info(
        json.loads(CREDENTIALS_JSON), scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def get_values(service, range_name):
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name
    ).execute()
    return result.get("values", [])


def read_inventory(service):
    rows = get_values(service, "Inventory!A3:G300")
    items = []
    for row in rows:
        if not row:
            continue
        comp = row[0].strip() if row else ""
        if not comp:
            continue
        cat = row[1].strip() if len(row) > 1 else ""
        if not cat:
            items.append({"type": "section", "label": comp})
            continue
        source  = row[2].strip() if len(row) > 2 else ""
        link    = row[3].strip() if len(row) > 3 else ""
        img_url = row[4].strip() if len(row) > 4 else ""
        qty_raw = row[5].strip() if len(row) > 5 else "1"
        notes   = row[6].strip() if len(row) > 6 else ""
        try:
            qty = int(float(qty_raw)) if qty_raw and qty_raw not in ("", "—") else 1
        except ValueError:
            qty = 1
        items.append({
            "type": "item", "component": comp, "category": cat,
            "source": source, "link": link, "img_url": img_url,
            "qty": qty, "notes": notes,
        })
    print(f"  Inventory: {len([i for i in items if i['type']=='item'])} parts, "
          f"{len([i for i in items if i['type']=='section'])} sections")
    return items


def read_allocations(service):
    rows = get_values(service, "Allocations!A3:F300")
    allocs = []
    for row in rows:
        if not row or not row[0].strip():
            continue
        comp    = row[0].strip()
        code    = row[1].strip() if len(row) > 1 else ""
        piece   = row[2].strip() if len(row) > 2 else ""
        qty_raw = row[3].strip() if len(row) > 3 else "1"
        status  = row[4].strip() if len(row) > 4 else ""
        notes   = row[5].strip() if len(row) > 5 else ""
        if not code:
            continue
        try:
            qty = int(float(qty_raw)) if qty_raw else 1
        except ValueError:
            qty = 1
        allocs.append({"component": comp, "code": code, "piece": piece,
                       "qty": qty, "status": status, "notes": notes})
    print(f"  Allocations: {len(allocs)} rows")
    return allocs


def read_projects(service):
    rows = get_values(service, "Projects!A3:D30")
    projects = {}
    skip = {"Build State options:", "Planning", "Parts sourcing",
            "Building", "Built", "Exhibited", "On hold"}
    for row in rows:
        if not row or not row[0].strip():
            continue
        code = row[0].strip()
        if code in skip:
            continue
        piece = row[1].strip() if len(row) > 1 else ""
        state = row[2].strip() if len(row) > 2 else "Planning"
        notes = row[3].strip() if len(row) > 3 else ""
        if code and piece:
            projects[code] = {"piece": piece, "state": state, "notes": notes}
    print(f"  Projects: {len(projects)} installations")
    return projects


def build_html(inventory, allocations, projects):
    alloc_by_code = {}
    for a in allocations:
        alloc_by_code.setdefault(a["code"], []).append(a)

    data = {
        "inventory": inventory,
        "allocations": alloc_by_code,
        "projects": projects,
        "state_colors": STATE_COLORS,
        "status_colors": STATUS_COLORS,
    }
    data_json = json.dumps(data)

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
    --rule: #d8d4cc; --green: #7aad7a; --yellow: #c8a84b; --gray: #9aacb2;
  }}
  html, body {{ background: transparent; }}
  body {{ font-family: 'EB Garamond', Georgia, serif; font-size: 18px;
    line-height: 1.65; color: var(--ink); padding: 0 0 120px; }}
  .view-toggle {{ padding: 44px 60px 0; display: flex; gap: 28px;
    border-bottom: 1px solid var(--rule); }}
  .view-tab {{ font-family: 'EB Garamond', Georgia, serif; font-size: 17px;
    color: var(--ink-light); background: transparent; border: none;
    border-bottom: 2px solid transparent; padding: 0 0 14px; cursor: pointer;
    font-style: italic; transition: color 0.15s; margin-bottom: -1px; }}
  .view-tab:hover {{ color: var(--ink); }}
  .view-tab.active {{ color: var(--ink); border-bottom-color: var(--ink); font-style: normal; }}
  .controls {{ padding: 40px 60px 0; display: flex; gap: 24px;
    align-items: center; flex-wrap: wrap; }}
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
  tbody td {{ font-size: 16px; padding: 11px 0; vertical-align: middle; color: var(--ink); }}
  .td-thumb {{ width: 96px; min-width: 96px; padding-right: 16px; }}
  .thumb-img {{ width: 96px; height: 96px; object-fit: cover; display: block;
    border-radius: 2px; cursor: zoom-in; }}
  .thumb-placeholder {{ width: 96px; height: 96px; background: #EBEBEB;
    border-radius: 2px; display: block; }}
  .td-component {{ font-size: 17px; min-width: 200px; }}
  .component-name {{ display: block; }}
  .component-notes {{ display: block; font-size: 14px; color: var(--ink-light);
    font-style: italic; margin-top: 2px; line-height: 1.4; }}
  .td-cat {{ font-size: 15px; color: var(--ink-mid); white-space: nowrap; padding-right: 24px; }}
  .td-qty {{ font-size: 15px; color: var(--ink-mid); white-space: nowrap; padding-right: 24px; }}
  tr.section-row td {{ font-size: 12px; letter-spacing: 0.12em; color: var(--ink-light);
    text-transform: uppercase; padding: 28px 0 8px; border-bottom: none; }}
  tr.section-row:hover {{ background: transparent; }}
  .empty-state {{ padding: 48px 60px; font-size: 15px; color: var(--ink-light); font-style: italic; }}
  .project-select-wrap {{ padding: 32px 60px 0; display: flex;
    align-items: baseline; gap: 16px; flex-wrap: wrap; }}
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
  .panel-header {{ margin-bottom: 24px; }}
  .panel-title {{ font-size: 24px; font-style: italic; margin-bottom: 8px; }}
  .panel-meta {{ font-size: 14px; color: var(--ink-light); display: flex;
    align-items: center; gap: 12px; }}
  .build-state-badge {{ font-size: 12px; font-style: normal; color: var(--ink);
    padding: 2px 10px; border-radius: 2px; white-space: nowrap; }}
  .alloc-table {{ width: 100%; border-collapse: collapse; border-top: 1px solid var(--rule); }}
  .alloc-table thead th {{ font-family: 'EB Garamond', Georgia, serif; font-size: 13px;
    font-weight: 400; color: var(--ink-light); text-align: left;
    padding: 8px 20px 8px 0; border-bottom: 1px solid var(--rule); letter-spacing: 0.03em; }}
  .alloc-table tbody tr {{ border-bottom: 1px solid var(--rule); transition: background 0.1s; }}
  .alloc-table tbody tr:hover {{ background: rgba(0,0,0,0.025); }}
  .alloc-table tbody td {{ font-size: 15px; padding: 12px 20px 12px 0;
    vertical-align: middle; color: var(--ink); }}
  .alloc-thumb {{ width: 48px; min-width: 48px; padding-right: 14px; }}
  .alloc-thumb-img {{ width: 48px; height: 48px; object-fit: cover;
    border-radius: 2px; cursor: zoom-in; display: block; }}
  .alloc-thumb-placeholder {{ width: 48px; height: 48px; background: #EBEBEB;
    border-radius: 2px; display: block; }}
  .status-badge {{ font-size: 12px; padding: 2px 10px; border-radius: 2px; white-space: nowrap; }}
  .alloc-qty {{ font-size: 14px; color: var(--ink-mid); }}
  .alloc-notes {{ font-size: 13px; color: var(--ink-light); font-style: italic; }}
  .no-allocs {{ padding: 24px 0; font-size: 15px; color: var(--ink-light); font-style: italic; }}
  #lightbox {{ position: fixed; inset: 0; background: rgba(0,0,0,0.85); z-index: 1000;
    cursor: pointer; align-items: center; justify-content: center; display: none; }}
  #lightbox-img {{ max-width: 90vw; max-height: 90vh; object-fit: contain; border-radius: 2px; }}
  @media (max-width: 768px) {{
    .view-toggle, .controls, .project-select-wrap, .table-wrap,
    .results-meta, .project-panel {{ padding-left: 24px; padding-right: 24px; }}
    .td-cat, .td-qty {{ display: none; }}
    .td-thumb {{ width: 64px; min-width: 64px; }}
    .thumb-img, .thumb-placeholder {{ width: 64px; height: 64px; }}
  }}
</style>
</head>
<body>

<div id="lightbox" onclick="closeLightbox()">
  <img id="lightbox-img" src="" alt="">
</div>

<div class="view-toggle">
  <button class="view-tab active" onclick="setView('inventory')">All parts</button>
  <button class="view-tab" onclick="setView('project')">By project</button>
</div>

<div id="inventory-view">
  <div class="controls">
    <div class="search-wrap">
      <input type="text" id="search"
        placeholder="Search components, categories, notes\u2026" oninput="filterTable()">
    </div>
    <div class="filter-group" id="cat-filters"></div>
  </div>
  <div class="results-meta" id="results-meta"></div>
  <div class="table-wrap">
    <table id="parts-table">
      <thead><tr>
        <th class="td-thumb"></th>
        <th>Component</th>
        <th>Category</th>
        <th>Qty</th>
      </tr></thead>
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
    <div class="panel-header">
      <div class="panel-title" id="panel-title"></div>
      <div class="panel-meta" id="panel-meta"></div>
    </div>
    <table class="alloc-table">
      <thead><tr>
        <th class="alloc-thumb"></th>
        <th>Component</th>
        <th>Category</th>
        <th>Qty</th>
        <th>Status</th>
        <th>Notes</th>
      </tr></thead>
      <tbody id="alloc-body"></tbody>
    </table>
    <div class="no-allocs" id="no-allocs" style="display:none;">
      No parts allocated to this piece yet.
    </div>
  </div>
</div>

<script>
const DATA         = {data_json};
const INVENTORY    = DATA.inventory;
const ALLOCS       = DATA.allocations;
const PROJECTS     = DATA.projects;
const STATE_COLORS = DATA.state_colors;
const STATUS_COLORS= DATA.status_colors;
let activeCategory = 'All';

const inventoryByName = {{}};
INVENTORY.filter(i => i.type === 'item').forEach(i => {{ inventoryByName[i.component] = i; }});

const categories = ['All', ...new Set(
  INVENTORY.filter(i => i.type==='item').map(i => i.category).filter(Boolean)
)].sort((a,b) => a==='All'?-1:b==='All'?1:a.localeCompare(b));

const catFilters = document.getElementById('cat-filters');
categories.forEach(cat => {{
  const btn = document.createElement('button');
  btn.className = 'filter-btn' + (cat==='All'?' active':'');
  btn.textContent = cat;
  btn.onclick = () => {{
    activeCategory = cat;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.toggle('active', b.textContent===cat));
    filterTable();
  }};
  catFilters.appendChild(btn);
}});

const tbody = document.getElementById('table-body');
INVENTORY.forEach(item => {{
  const tr = document.createElement('tr');
  if (item.type === 'section') {{
    tr.className = 'section-row';
    tr.innerHTML = `<td colspan="4">${{item.label}}</td>`;
  }} else {{
    tr.dataset.component = item.component.toLowerCase();
    tr.dataset.category  = item.category;
    tr.dataset.notes     = (item.notes||'').toLowerCase();
    const thumb = item.img_url
      ? `<img src="${{item.img_url}}" class="thumb-img" onclick="openLightbox('${{item.img_url}}','${{item.component}}')">`
      : `<div class="thumb-placeholder"></div>`;
    tr.innerHTML = `
      <td class="td-thumb">${{thumb}}</td>
      <td class="td-component">
        <span class="component-name">${{item.component}}</span>
        ${{item.notes?`<span class="component-notes">${{item.notes}}</span>`:''}}
      </td>
      <td class="td-cat">${{item.category}}</td>
      <td class="td-qty">${{item.qty}}</td>`;
  }}
  tbody.appendChild(tr);
}});

function filterTable() {{
  const q = document.getElementById('search').value.toLowerCase().trim();
  const rows = tbody.querySelectorAll('tr');
  let visible=0, lastSec=null, lastSecVis=false;
  rows.forEach(tr => {{
    if (tr.classList.contains('section-row')) {{
      if (lastSec) lastSec.classList.toggle('hidden', !lastSecVis);
      lastSec=tr; lastSecVis=false; return;
    }}
    const mQ = !q||tr.dataset.component.includes(q)||tr.dataset.notes.includes(q)||(tr.dataset.category||'').toLowerCase().includes(q);
    const mC = activeCategory==='All'||tr.dataset.category===activeCategory;
    const show = mQ&&mC;
    tr.classList.toggle('hidden',!show);
    if(show){{visible++;lastSecVis=true;}}
  }});
  if(lastSec) lastSec.classList.toggle('hidden',!lastSecVis);
  const total = INVENTORY.filter(i=>i.type==='item').length;
  document.getElementById('results-meta').textContent =
    (q||activeCategory!=='All')?`${{visible}} of ${{total}} parts`:`${{total}} parts`;
  document.getElementById('empty-state').style.display = visible===0?'block':'none';
}}

const pillsEl = document.getElementById('project-pills');
Object.entries(PROJECTS).sort((a,b)=>a[1].piece.localeCompare(b[1].piece)).forEach(([code,proj])=>{{
  const btn = document.createElement('button');
  btn.className = 'project-pill';
  btn.textContent = `${{proj.piece}} (${{code}})`;
  btn.onclick = ()=>{{
    document.querySelectorAll('.project-pill').forEach(b=>b.classList.toggle('active',b===btn));
    showProjectPanel(code);
  }};
  pillsEl.appendChild(btn);
}});

function showProjectPanel(code) {{
  const proj   = PROJECTS[code]||{{}};
  const state  = proj.state||'Planning';
  const stCol  = STATE_COLORS[state]||'#F0F0F0';
  const allocs = ALLOCS[code]||[];
  document.getElementById('panel-title').textContent = proj.piece||code;
  document.getElementById('panel-meta').innerHTML =
    `${{allocs.length}} part${{allocs.length!==1?'s':''}} allocated
     <span class="build-state-badge" style="background:${{stCol}}">${{state}}</span>`;
  const allocBody = document.getElementById('alloc-body');
  allocBody.innerHTML='';
  allocs.forEach(a=>{{
    const inv  = inventoryByName[a.component]||{{}};
    const thumb= inv.img_url
      ? `<img src="${{inv.img_url}}" class="alloc-thumb-img" onclick="openLightbox('${{inv.img_url}}','${{a.component}}')">`
      : `<div class="alloc-thumb-placeholder"></div>`;
    const stBg = STATUS_COLORS[a.status]||'#F0F0F0';
    const tr   = document.createElement('tr');
    tr.innerHTML=`
      <td class="alloc-thumb">${{thumb}}</td>
      <td class="td-component">
        <span class="component-name">${{a.component}}</span>
        ${{inv.notes?`<span class="component-notes">${{inv.notes}}</span>`:''}}
      </td>
      <td class="td-cat">${{inv.category||''}}</td>
      <td class="alloc-qty">${{a.qty}}</td>
      <td><span class="status-badge" style="background:${{stBg}}">${{a.status}}</span></td>
      <td class="alloc-notes">${{a.notes}}</td>`;
    allocBody.appendChild(tr);
  }});
  document.getElementById('no-allocs').style.display=allocs.length===0?'block':'none';
  document.getElementById('project-panel').classList.add('visible');
}}

function setView(view) {{
  document.getElementById('inventory-view').style.display=view==='inventory'?'block':'none';
  document.getElementById('project-view').style.display=view==='project'?'block':'none';
  document.querySelectorAll('.view-tab').forEach((t,i)=>
    t.classList.toggle('active',(i===0&&view==='inventory')||(i===1&&view==='project')));
}}

function openLightbox(src,alt) {{
  document.getElementById('lightbox-img').src=src;
  document.getElementById('lightbox-img').alt=alt;
  document.getElementById('lightbox').style.display='flex';
  document.body.style.overflow='hidden';
}}
function closeLightbox() {{
  document.getElementById('lightbox').style.display='none';
  document.body.style.overflow='';
}}
document.addEventListener('keydown',e=>{{if(e.key==='Escape')closeLightbox();}});
filterTable();
</script>
</body>
</html>"""


def main():
    print("Connecting to Google Sheets...")
    service = get_service()
    print("Reading Inventory tab...")
    inventory = read_inventory(service)
    print("Reading Allocations tab...")
    allocations = read_allocations(service)
    print("Reading Projects tab...")
    projects = read_projects(service)
    print("Generating index.html...")
    html = build_html(inventory, allocations, projects)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Done — wrote {len(html):,} chars to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
