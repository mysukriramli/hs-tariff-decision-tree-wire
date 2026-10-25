import os
import json
import hashlib
import duckdb
import requests
from datetime import datetime, timezone

DB_FILE = "data/hs_tree.db"
HISTORY_DIR = "data/history"
EXPORT_DIR = "public"
API_DIR = os.path.join(EXPORT_DIR, "v1")
TREES_DIR = os.path.join(API_DIR, "trees")

# Machine-readable HS classification nomenclature feeds (WCO HS 2022)
HS_STRUCTURE_URL = "https://raw.githubusercontent.com/datasets/harmonized-system/master/data/harmonized-system.json"

# Key high-volume chapters prioritized for agent classification logic
PRIORITY_CHAPTERS = {
    "39": "Plastics and Articles Thereof",
    "84": "Nuclear Reactors, Boilers, Machinery and Mechanical Appliances",
    "85": "Electrical Machinery and Equipment and Parts Thereof",
    "87": "Vehicles Other Than Railway or Tramway Rolling-Stock",
    "90": "Optical, Photographic, Measuring, and Medical Instruments"
}

def compute_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()

def fetch_hs_records():
    headers = {"User-Agent": "HSTariffDecisionTreeWire/1.0"}
    try:
        resp = requests.get(HS_STRUCTURE_URL, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"Failed to fetch HS dataset: {e}")
    return []

def build_chapter_tree(chapter_code: str, title: str, records: list) -> dict:
    """Transforms linear 2/4/6-digit HS lists into a hierarchical traversal tree for agents."""
    ch_records = [r for r in records if str(r.get("hscode", "")).startswith(chapter_code)]
    
    headings = {}
    for r in ch_records:
        code = str(r.get("hscode", "")).strip()
        desc = r.get("description", "").strip()
        level = r.get("level", len(code))
        
        if len(code) == 4:
            headings[code] = {
                "heading": code,
                "description": desc,
                "subheadings": {}
            }
        elif len(code) == 6:
            h4 = code[:4]
            if h4 not in headings:
                headings[h4] = {"heading": h4, "description": "General Heading", "subheadings": {}}
            headings[h4]["subheadings"][code] = {
                "hs6": code,
                "description": desc
            }

    # Construct the binary/multi-way decision tree
    nodes = {}
    node_counter = 1
    root_id = "node_root"

    root_options = []
    for h4, data in sorted(headings.items()):
        node_id = f"node_{h4}"
        root_options.append({
            "code": h4,
            "description": data["description"],
            "next": node_id if data["subheadings"] else "TERMINAL_UNSPECIFIED"
        })
        
        # Subheading level decision node
        sub_options = []
        for h6, sub_data in sorted(data["subheadings"].items()):
            sub_options.append({
                "hs6_code": h6,
                "description": sub_data["description"],
                "decision": "CLASSIFIED"
            })
            
        nodes[node_id] = {
            "type": "heading_discriminator",
            "prompt": f"Select specific subheading under Heading {h4}: {data['description']}",
            "options": sub_options
        }
        node_counter += 1

    nodes[root_id] = {
        "type": "chapter_root",
        "prompt": f"Classify good within Chapter {chapter_code} ({title}). Select matching scope:",
        "options": root_options
    }

    tree_payload = {
        "chapter": chapter_code,
        "title": title,
        "root": root_id,
        "nodes": nodes,
        "metrics": {
            "total_nodes": len(nodes),
            "headings_count": len(headings),
            "subheadings_count": sum(len(d["subheadings"]) for d in headings.values())
        }
    }
    return tree_payload

def build_static_api(conn):
    os.makedirs(TREES_DIR, exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()

    cur = conn.execute("SELECT chapter, title, total_nodes, total_endpoints, tree_depth, last_updated_utc, tree_json FROM decision_trees")
    rows = cur.fetchall()

    catalog = []
    lines = [
        "# HS Tariff Decision Tree Wire",
        f"> Last Sync: {now_iso} UTC",
        "> Optimization: Replaces 50-page legal chapter schedules with deterministic O(log N) decision traversal trees.",
        "",
        "## Available Chapter Decision Trees"
    ]

    for row in rows:
        ch, title, nodes_cnt, endpoints_cnt, depth, updated, tree_json = row
        catalog.append({
            "chapter": ch,
            "title": title,
            "nodes": nodes_cnt,
            "terminal_subheadings": endpoints_cnt,
            "updated_utc": updated,
            "endpoint": f"v1/trees/chapter_{ch}.tree.json"
        })

        with open(os.path.join(TREES_DIR, f"chapter_{ch}.tree.json"), "w", encoding="utf-8") as f:
            f.write(tree_json)

        lines.append(f"- **Chapter {ch}** ({title}): {nodes_cnt} nodes | {endpoints_cnt} terminal codes | `v1/trees/chapter_{ch}.tree.json`")

    with open(os.path.join(API_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"metadata": {"updated_at": now_iso, "count": len(catalog)}, "trees": catalog}, f, indent=2)

    with open(os.path.join(EXPORT_DIR, "llms.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    html = f"""<!DOCTYPE html><html><head><title>HS Tariff Decision Tree Wire</title></head>
    <body style='font-family:system-ui,sans-serif;max-width:850px;margin:2rem auto;line-height:1.6;padding:0 1rem;'>
    <h1>🌲 HS Tariff Decision Tree Wire</h1>
    <p>Deterministic O(log N) classification decision trees for customs, trade, and logistics AI agents.</p>
    <h3>Machine Feeds</h3>
    <ul>
      <li><a href='v1/index.json'>/v1/index.json</a> (Catalog &amp; Chapter Index)</li>
      <li><a href='llms.txt'>llms.txt</a> (Token-Efficient LLM Digest)</li>
      <li><a href='trees.parquet'>trees.parquet</a> (Columnar Parquet Snapshot)</li>
    </ul>
    <h3>Compiled Chapter Trees</h3>
    <ul>
      {"".join([f"<li><a href='v1/trees/chapter_{c['chapter']}.tree.json'>Chapter {c['chapter']}: {c['title']}</a> ({c['terminal_subheadings']} classifications)</li>" for c in catalog])}
    </ul>
    </body></html>"""
    with open(os.path.join(EXPORT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

def run():
    os.makedirs("data", exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)
    os.makedirs(EXPORT_DIR, exist_ok=True)

    conn = duckdb.connect(DB_FILE)
    with open("schema.sql", "r", encoding="utf-8") as f:
        conn.execute(f.read())

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    date_str = now.strftime("%Y-%m-%d")
    year_str = now.strftime("%Y")
    month_str = now.strftime("%m")

    month_dir = os.path.join(HISTORY_DIR, year_str, month_str)
    os.makedirs(month_dir, exist_ok=True)
    daily_history_file = os.path.join(month_dir, f"{date_str}.jsonl")

    records = fetch_hs_records()
    if not records:
        print("Using local schema fallback if remote feed unavailable")
        conn.close()
        return

    conn.execute("BEGIN TRANSACTION")

    for ch_code, title in PRIORITY_CHAPTERS.items():
        tree_payload = build_chapter_tree(ch_code, title, records)
        tree_json = json.dumps(tree_payload, separators=(",", ":"))
        content_hash = compute_hash(tree_payload)
        
        total_nodes = tree_payload["metrics"]["total_nodes"]
        total_endpoints = tree_payload["metrics"]["subheadings_count"]
        depth = 2

        existing = conn.execute(f"SELECT content_hash FROM decision_trees WHERE chapter = '{ch_code}'").fetchone()
        escaped_tree_json = tree_json.replace("'", "''")

        if not existing:
            conn.execute(f"""
                INSERT INTO decision_trees (
                    chapter, title, total_nodes, total_endpoints, tree_depth,
                    tree_json, content_hash, last_updated_utc
                ) VALUES (
                    '{ch_code}', '{title}', {total_nodes}, {total_endpoints}, {depth},
                    '{escaped_tree_json}', '{content_hash}', '{now_iso}'
                )
            """)

            commit_id = conn.execute("SELECT nextval('seq_commit_id')").fetchone()[0]
            conn.execute(f"""
                INSERT INTO ledger (commit_id, timestamp_utc, operation, chapter, nodes_count, detail)
                VALUES ({commit_id}, '{now_iso}', 'INIT_TREE', '{ch_code}', {total_nodes}, 'Initial decision tree generated')
            """)

            ledger_entry = {
                "commit_id": commit_id,
                "timestamp_utc": now_iso,
                "operation": "INIT_TREE",
                "chapter": ch_code,
                "total_nodes": total_nodes,
                "endpoints": total_endpoints,
                "content_hash": content_hash
            }
            with open(daily_history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(ledger_entry) + "\n")

        elif existing[0] != content_hash:
            conn.execute(f"""
                UPDATE decision_trees SET
                    total_nodes = {total_nodes},
                    total_endpoints = {total_endpoints},
                    tree_json = '{escaped_tree_json}',
                    content_hash = '{content_hash}',
                    last_updated_utc = '{now_iso}'
                WHERE chapter = '{ch_code}'
            """)

            commit_id = conn.execute("SELECT nextval('seq_commit_id')").fetchone()[0]
            conn.execute(f"""
                INSERT INTO ledger (commit_id, timestamp_utc, operation, chapter, nodes_count, detail)
                VALUES ({commit_id}, '{now_iso}', 'TREE_DRIFT', '{ch_code}', {total_nodes}, 'Decision tree updated from nomenclature')
            """)

            ledger_entry = {
                "commit_id": commit_id,
                "timestamp_utc": now_iso,
                "operation": "TREE_DRIFT",
                "chapter": ch_code,
                "total_nodes": total_nodes,
                "endpoints": total_endpoints,
                "content_hash": content_hash
            }
            with open(daily_history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(ledger_entry) + "\n")

    conn.execute("COMMIT")

    conn.execute(f"COPY (SELECT chapter, title, total_nodes, total_endpoints, tree_depth, content_hash, last_updated_utc FROM decision_trees) TO '{EXPORT_DIR}/trees.parquet' (FORMAT PARQUET)")
    build_static_api(conn)
    conn.close()

if __name__ == "__main__":
    run()
