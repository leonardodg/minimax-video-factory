#!/usr/bin/env python3
"""api2ui.py — Convert an API-format workflow into a ComfyUI litegraph (UI) JSON.

The inverse of ui2api.py, and the reason it exists: the MCP server submits API
format, while the browser can only open UI format. Maintaining the same graph
twice, by hand, guarantees they drift. Keep the API file as the single source of
truth -- it is the one that actually renders -- and generate the UI file from it.

Approach (mirrors ui2api.py so the round trip is stable):
  1. Load the API workflow: {"<id>": {"class_type": ..., "inputs": {...}}}.
  2. Fetch /object_info to learn each node's declared input order. That order is
     what decides both the input-slot indices and which values are widgets, so
     it has to come from the server, never from a guess.
  3. Split each input: a ["<id>", slot] value becomes a link; anything else
     becomes a widget value, emitted in declaration order.
  4. Lay the nodes out in dependency depth columns so the graph opens readable
     instead of as a pile at the origin.

Usage:
  python3 scripts/api2ui.py <input_api.json> <output_ui.json> [--comfy-url URL]
  python3 scripts/api2ui.py in.json out.json --title "ROSY — Reel turbo"
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

PRIMITIVE_TYPES = {"STRING", "INT", "FLOAT", "COMBO", "BOOLEAN"}

COL_W, ROW_H, NODE_W = 340, 190, 300


def fetch_object_info(url: str) -> dict:
    req = urllib.request.Request(f"{url}/object_info")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def is_primitive(info) -> bool:
    """Widget or socket? Must agree with ui2api.is_primitive, or the round trip
    moves a value between the widget list and the input list and corrupts both."""
    if not info:
        return False
    t = info[0] if isinstance(info, list) and info else info
    # A COMBO arrives as the list of its choices, e.g. ['a.safetensors', ...].
    if isinstance(t, list):
        return True
    if not isinstance(t, str):
        return False
    # V3-schema widget types have generated names: SaveVideo.codec is
    # COMFY_DYNAMICCOMBO_V3. Match the family, not each new name.
    return t in PRIMITIVE_TYPES or t.startswith("COMFY_DYNAMICCOMBO")


def slot_type(info) -> str:
    t = info[0] if isinstance(info, list) and info else info
    if isinstance(t, list):
        return "COMBO"
    return t if isinstance(t, str) else "*"


def inputs_ordered(node_def: dict) -> list[tuple[str, object]]:
    src = node_def.get("input", {})
    return list(src.get("required", {}).items()) + list(src.get("optional", {}).items())


def depths(api: dict) -> dict[str, int]:
    """Dependency depth per node, for column layout. Cycles are impossible in a
    ComfyUI graph, but guard anyway so a malformed file cannot hang this."""
    memo: dict[str, int] = {}

    def depth(nid: str, seen: frozenset) -> int:
        if nid in memo:
            return memo[nid]
        if nid in seen:
            return 0
        best = 0
        for v in api.get(nid, {}).get("inputs", {}).values():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                best = max(best, depth(v[0], seen | {nid}) + 1)
        memo[nid] = best
        return best

    return {nid: depth(nid, frozenset()) for nid in api}


def convert(api: dict, obj_info: dict, title: str) -> dict:
    col = depths(api)
    rows: dict[int, int] = {}
    pos: dict[str, list[int]] = {}
    for nid in sorted(api, key=lambda k: (col[k], int(k) if k.isdigit() else 0)):
        c = col[nid]
        r = rows.get(c, 0)
        rows[c] = r + 1
        pos[nid] = [80 + c * COL_W, 80 + r * ROW_H]

    nodes, links = [], []
    link_id = 0
    # A node's output slot index is its position in the class's output list.
    # Every link needs it, so resolve it once per source node.
    for nid in sorted(api, key=lambda k: int(k) if k.isdigit() else 0):
        node = api[nid]
        ntype = node["class_type"]
        ndef = obj_info.get(ntype)
        if ndef is None:
            raise SystemExit(
                f"node type '{ntype}' (id {nid}) is unknown to this ComfyUI. "
                f"Is its custom node pack installed?"
            )
        ordered = inputs_ordered(ndef)
        api_inputs = node.get("inputs", {})

        in_slots, widgets = [], []
        for name, info in ordered:
            val = api_inputs.get(name)
            linked = isinstance(val, list) and len(val) == 2 and isinstance(val[0], str)
            if linked:
                in_slots.append({"name": name, "type": slot_type(info),
                                 "link": None, "_src": val})
            elif is_primitive(info):
                # Omitted primitives fall back to the declared default, so the
                # widget list stays aligned with the declaration order.
                if name in api_inputs:
                    widgets.append(val)
                else:
                    d = info[1].get("default") if (isinstance(info, list) and len(info) > 1
                                                   and isinstance(info[1], dict)) else None
                    widgets.append(d)
            else:
                in_slots.append({"name": name, "type": slot_type(info), "link": None})

        outs = ndef.get("output", []) or []
        out_names = ndef.get("output_name") or outs
        nodes.append({
            "id": int(nid), "type": ntype, "pos": pos[nid],
            "size": [NODE_W, 60 + 26 * max(len(in_slots) + len(widgets), 1)],
            "flags": {}, "order": col[nid], "mode": 0,
            "inputs": in_slots,
            "outputs": [{"name": (out_names[i] if i < len(out_names) else str(o)),
                         "type": o, "links": [], "slot_index": i}
                        for i, o in enumerate(outs)],
            "properties": {"Node name for S&R": ntype},
            "widgets_values": widgets,
        })

    by_id = {n["id"]: n for n in nodes}
    for n in nodes:
        for slot_idx, inp in enumerate(n["inputs"]):
            src = inp.pop("_src", None)
            if src is None:
                continue
            from_id, from_slot = int(src[0]), int(src[1])
            link_id += 1
            inp["link"] = link_id
            links.append([link_id, from_id, from_slot, n["id"], slot_idx, inp["type"]])
            out = by_id[from_id]["outputs"]
            if from_slot < len(out):
                out[from_slot]["links"].append(link_id)

    return {
        "id": title.lower().replace(" ", "-")[:60],
        "revision": 0,
        "last_node_id": max((n["id"] for n in nodes), default=0),
        "last_link_id": link_id,
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {"generated_by": "scripts/api2ui.py", "title": title},
        "version": 0.4,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Convert an API workflow JSON to ComfyUI UI format.")
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    p.add_argument("--title", default="workflow")
    a = p.parse_args()

    with open(a.input) as f:
        api = json.load(f)
    ui = convert(api, fetch_object_info(a.comfy_url), a.title)
    with open(a.output, "w") as f:
        json.dump(ui, f, indent=2)
    print(f"wrote {a.output}: {len(ui['nodes'])} nodes, {len(ui['links'])} links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
