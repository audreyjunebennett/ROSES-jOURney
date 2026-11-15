"""Compare catalog schematics after converting them with published/inspect_templates.py."""

import argparse
from collections import Counter
import json
from pathlib import Path
import time

import nbtlib

from mechanism_lab import Lab, place, put, require, totals, xyz


TARGET = "minecraft:cobbled_deepslate"
BOX = "minecraft:shulker_box"
CART = "minecraft:hopper_minecart"
MIXED = [(TARGET, 47), ("minecraft:dirt", 13)]
HARDWARE = {"minecraft:" + kind for kind in ("chest", "barrel", "hopper", "dropper", "dispenser", "shulker_box")}


def totals_with_boxes(stacks):
    counts = totals(stacks)
    for stack in stacks:
        counts.update(totals(entry["item"] for entry in stack.get("components", {}).get("minecraft:container", [])))
    return counts


def box_item(payload):
    if not payload:
        return BOX
    entries = ",".join(f'{{slot:{slot},item:{{id:"{item}",count:{count}}}}}'
                       for slot, (item, count) in enumerate(payload))
    return f"{BOX}[minecraft:container=[{entries}]]"


LAYOUTS = {
    "bu010": dict(base=(16, 80, 48), intake=(0, 4, 5), box=(0, 4, 4), items=(0, 3, 5), empty=(0, 1, 4)),
    "bu002": dict(base=(40, 80, 48), intake=(0, 6, 1), box=(0, 3, 1), items=(0, 0, 0), empty=(1, 2, 2)),
    "bu008": dict(base=(80, 80, 48), intake=(2, 7, 2), box=(1, 6, 2), items=(1, -1, -1), empty=(1, 3, -1)),
}


def origin(base, delta):
    return tuple(a + b for a, b in zip(base, delta))


def build(lab, server, name):
    layout = LAYOUTS[name]
    base = layout["base"]
    x, y, z = base
    lab.command(f"fill {x-4} {y-1} {z-5} {x+7} {y+9} {z+8} minecraft:air", "No blocks were filled")
    for entity in ("minecraft:item", CART):
        lab.command(f"kill @e[type={entity},x={x},y={y+4},z={z+2},distance=..10]", "No entity was found")
    lab.command(f"fill {x-4} {y-1} {z-5} {x+7} {y-1} {z+8} minecraft:smooth_stone")
    lab.command(f"place template roses:{name} {xyz(base)} none none 1.0 0 strict")
    result = {key: origin(base, delta) for key, delta in layout.items() if key != "base"}
    if name != "bu010":
        place(lab, result["items"], "minecraft:chest")
        place(lab, result["empty"], "minecraft:chest")
    if name == "bu008":
        for slot in ("items", "empty"):
            a, b, c = result[slot]
            place(lab, (a, b+1, c), "minecraft:hopper[facing=down]")
    template = nbtlib.load(server / f"fixture-world/generated/roses/structure/{name}.nbt")
    result["hardware"] = {origin(base, tuple(int(n) for n in b["pos"])) for b in template["blocks"] if "nbt" in b}
    result["hardware"].update(result[key] for key in ("items", "intake", "empty", "box"))
    if name == "bu008":
        result["hardware"].update((result[key][0], result[key][1]+1, result[key][2]) for key in ("items", "empty"))
    result["center"] = (x, y+4, z+2)
    lab.sprint(100)
    return result


def snapshot(lab, rig):
    tick = lab.game_time()
    containers = []
    for pos in sorted(rig["hardware"]):
        if lab.block(pos)["id"] in HARDWARE:
            containers.extend(lab.inventory(pos))
    loose = lab.items(rig["center"], 10)
    carts = lab.rpc("entities.query", dimension="minecraft:overworld", center=dict(zip("xyz", rig["center"])),
                    radius=10, types=[CART])
    for entity in carts["entities"]:
        containers.extend(lab.nbt(f"entity {entity['uuid']}").get("Items", []))
    expected = totals_with_boxes(containers + [i["stack"] for i in loose])
    expected[CART] += carts["total"]
    box = lab.block(rig["box"])
    if box["id"] == BOX:
        expected[BOX] += 1
    report = {"tick": tick, "items": lab.inventory(rig["items"]), "returned": lab.inventory(rig["empty"]),
              "all": dict(expected), "loose": loose, "cart_entities": carts["total"],
              "input_box_present": box["id"] == BOX}
    require(lab.game_time() == tick, "simulation advanced during snapshot")
    return report


def case(lab, rig, payload, name, intervals):
    before = snapshot(lab, rig)
    added = Counter({BOX: 1})
    for item, count in payload:
        added[item] += count
    put(lab, rig["intake"], 0, box_item(payload))
    phases = []
    for span in intervals:
        lab.sprint(span)
        phases.append(snapshot(lab, rig))
    after = phases[-1]
    expected = Counter(before["all"]) + added
    expected_items = Counter({key: value for key, value in added.items() if key != BOX})
    intact = all(Counter(sample["all"]) == expected for sample in phases)
    detected = all(totals_with_boxes(sample["returned"])[BOX] <= added[BOX] for sample in phases)
    recovered = totals(after["items"]) == expected_items and totals(after["returned"]) == Counter({BOX: 1})
    if recovered:
        recovered = not any(stack.get("components", {}).get("minecraft:container") for stack in after["returned"])
    result = {"case": name, "before": before, "input": dict(added), "snapshots": phases,
              "conserved_at_every_checkpoint": intact, "returned_box_count_valid": detected,
              "exact_outputs": recovered}
    return result


def backlog(lab, server, name):
    rig = build(lab, server, name)
    blocking_item = "minecraft:bedrock"
    for slot in range(27):
        put(lab, rig["items"], slot, blocking_item, 64)
    charged = snapshot(lab, rig)
    put(lab, rig["intake"], 0, box_item([(TARGET, 64)] * 27))
    lab.sprint(6200)
    held = snapshot(lab, rig)
    incoming = Counter({TARGET: 1728, BOX: 1})
    require(Counter(held["all"]) == Counter(charged["all"]) + incoming
            and not held["loose"] and not held["returned"], f"{name}: backlog dropped or prematurely returned input")
    lab.command(f"data remove block {xyz(rig['items'])} Items")
    lab.sprint(15_000)
    released = snapshot(lab, rig)
    expected = Counter(charged["all"]) + incoming
    expected[blocking_item] -= 1728
    require(Counter(released["all"]) == expected and totals(released["items"]) == Counter({TARGET: 1728})
            and totals_with_boxes(released["returned"]) == Counter({BOX: 1}),
            f"{name}: backlog recovery lost items")
    return {"case": "backlog", "loaded_output_blockers": charged, "while_blocked": held, "after_clear": released}


def consecutive(lab, server, name):
    rig = build(lab, server, name)
    initial = snapshot(lab, rig)
    put(lab, rig["intake"], 0, box_item(MIXED))
    put(lab, rig["intake"], 1, box_item(MIXED))
    put(lab, rig["intake"], 2, box_item([]))
    lab.sprint(1600)
    final = snapshot(lab, rig)
    expected = Counter({TARGET: 94, "minecraft:dirt": 26})
    require(Counter(final["all"]) == Counter(initial["all"]) + expected + Counter({BOX: 3})
            and totals(final["items"]) == expected and totals_with_boxes(final["returned"]) == Counter({BOX: 3}),
            f"{name}: consecutive boxes did not drain cleanly")
    return {"case": "consecutive", "before": initial, "after": final}


def run(lab, server, name):
    cases = []
    for trial, payload, checkpoints in [
        ("mixed", MIXED, (20, 100, 400, 700)),
        ("empty", [], (20, 100, 400, 700)),
        ("full", [(TARGET, 64)] * 27, (121, 800, 3000, 3400, 7100)),
    ]:
        rig = build(lab, server, name)
        result = case(lab, rig, payload, trial, checkpoints)
        print(name, trial, "exact", result["exact_outputs"], "conserved", result["conserved_at_every_checkpoint"],
              "at", result["snapshots"][-1]["tick"] - result["before"]["tick"], "gt", flush=True)
        cases.append(result)
    if name in {"bu002", "bu010"}:
        cases.append(backlog(lab, server, name))
        print(name, "passed full-output backlog and recovery", flush=True)
        cases.append(consecutive(lab, server, name))
        print(name, "passed three consecutive boxes", flush=True)
    return cases


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("server", type=Path)
    parser.add_argument("modules", nargs="+", choices=LAYOUTS)
    args = parser.parse_args()
    lab = Lab(args.server)
    lab.command("forceload add 0 32 95 63", "No chunks were marked")
    time.sleep(2)
    try:
        lab.command("tick freeze", "already frozen")
        for module in args.modules:
            report = run(lab, args.server, module)
            Path(__file__).with_name(f"{module}-comparison.json").write_text(json.dumps(report, indent=2))
    finally:
        lab.command("tick unfreeze")
        lab.command("forceload remove 0 32 95 63")
