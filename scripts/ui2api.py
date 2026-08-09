#!/usr/bin/env python3
"""ui2api.py — Convert a ComfyUI litegraph workflow JSON (UI format) into API format.

API format is what ComfyUI's `POST /prompt` endpoint accepts:
    { "<node_id>": {"class_type": "<type>", "inputs": { "<input_name>": value } } }

Approach:
  1. Load the UI workflow JSON (nodes + links).
  2. Fetch ComfyUI `/object_info` to learn each node's INPUT_TYPES (required + optional)
     and the widget ordering, so widget values map to the correct input names.
  3. For each input:
       - if connected via a link -> ["<from_node_id>", <from_slot>]
       - else pop the next primitive widget value (STRING/INT/FLOAT/COMBO/BOOLEAN)
     Non-primitive inputs (IMAGE/VIDEO/AUDIO/MODEL/...) without a link are left null.

Usage:
  python3 scripts/ui2api.py <input_ui.json> <output_api.json> [--comfy-url http://127.0.0.1:8188]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

# ComfyUI primitive input types (map to widget values)
PRIMITIVE_TYPES = {
    "STRING", "INT", "FLOAT", "COMBO", "BOOLEAN",
}


def fetch_object_info(url: str) -> dict:
    req = urllib.request.Request(f"{url}/object_info")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def is_primitive(info: dict) -> bool:
    if not info:
        return False
    t = info.get("type", "")
    if t in PRIMITIVE_TYPES:
        return True
    # "INT" etc. may be wrapped: ['INT', {'default': ...}]
    return isinstance(t, list) and bool(t) and t[0] in PRIMITIVE_TYPES


def inputs_ordered(node_def: dict) -> list[dict]:
    """Return list of {name, info} in ComfyUI's declaration order."""
    out = []
    req = node_def.get("input", {}).get("required", {})
    opt = node_def.get("input", {}).get("optional", {})
    for name, info in list(req.items()) + list(opt.items()):
        out.append({"name": name, "info": info})
    return out


def convert(ui: dict, obj_info: dict, comfy_url: str) -> dict:
    api: dict[str, dict] = {}

    # index links: (to_node, to_slot) -> (from_node, from_slot)
    link_map: dict[tuple[int, int], tuple[int, int]] = {}
    for link in ui.get("links", []):
        if len(link) < 5:
            continue
        _link_id, from_node, from_slot, to_node, to_slot = link[:5]
        link_map[(to_node, to_slot)] = (from_node, from_slot)

    for node in ui.get("nodes", []):
        node_type = node.get("type")
        nid = node.get("id")
        if node.get("mode") == 4:  # bypassed
            continue
        if node_type is None:
            continue
        if node_type == "MarkdownNote":
            continue

        # inputs by name from the UI (with connected link or widget name)
        ui_inputs: dict[str, dict] = {}
        for inp in node.get("inputs", []):
            ui_inputs[inp.get("name")] = inp

        widget_values = list(node.get("widgets_values", []))

        node_def = obj_info.get(node_type, {})
        ordered = inputs_ordered(node_def)

        api_inputs: dict[str, object] = {}
        for idx, slot in enumerate(ordered):
            name = slot["name"]
            info = slot["info"]
            ui_inp = ui_inputs.get(name)

            if ui_inp and ui_inp.get("link") is not None:
                src = link_map.get((nid, idx))
                # Fallback: match by slot index from UI inputs
                if src is None:
                    src = link_map.get((nid, ui_inp["link"]))
                if src:
                    api_inputs[name] = list(src)
                continue

            # No link -> try to consume a primitive widget value.
            # If no widget value is left, omit it (ComfyUI uses the default).
            if is_primitive(info) and widget_values:
                api_inputs[name] = widget_values.pop(0)
            # non-primitive without link -> leave out (null/default)

        # SaveVideo: ensure filename_prefix exists (usually first widget)
        api[nid] = {"class_type": node_type, "inputs": api_inputs}

    return api


def main() -> int:
    p = argparse.ArgumentParser(description="Convert ComfyUI UI workflow JSON to API format.")
    p.add_argument("input_ui", help="Path to UI-format workflow JSON")
    p.add_argument("output_api", help="Path to write API-format JSON")
    p.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    p.add_argument("--no-fetch", action="store_true",
                   help="Skip object_info fetch; emit API JSON anyway (best-effort).")
    args = p.parse_args()

    with open(args.input_ui) as f:
        ui = json.load(f)

    obj_info = {} if args.no_fetch else fetch_object_info(args.comfy_url)

    api = convert(ui, obj_info, args.comfy_url)
    with open(args.output_api, "w") as f:
        json.dump(api, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(api)} nodes to {args.output_api}")
    for nid, node in api.items():
        ct = node["class_type"]
        keys = ",".join(node["inputs"].keys())
        print(f"  {nid}: {ct}  [{keys}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
