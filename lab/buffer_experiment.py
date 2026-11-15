"""Compare a short recirculating water collector with two stationary hopper carts."""

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import time

from mechanism_lab import Lab, place, put, require, totals, xyz


HOPPER = "minecraft:hopper_minecart"
FILLER = "minecraft:bedrock"
PAYLOAD = [
    ("minecraft:cobbled_deepslate", 64), ("minecraft:cobbled_deepslate", 19),
    ("minecraft:dirt", 17), ("minecraft:gravel", 32), ("minecraft:iron_sword", 1),
]
DIRECTIONS = {(1, 0): "east", (0, 1): "south", (-1, 0): "west", (0, -1): "north"}


@dataclass
class Fixture:
    name: str
    center: tuple
    radius: int
    inputs: list
    storage: dict
    outputs: set
    carts: dict
    footprint: str


def set_block(lab, pos, state):
    place(lab, pos, "minecraft:" + state)


def build_water(lab):
    corners = [(32, 0), (38, 0), (38, 6), (32, 6)]
    vectors = list(DIRECTIONS)
    lab.command("fill 31 197 -1 39 204 7 minecraft:air", "No blocks were filled")
    lab.command("fill 31 201 -1 39 201 7 minecraft:glass")
    storage, outputs = {}, set()
    for side, (x, z) in enumerate(corners):
        dx, dz = vectors[side]
        corner = (x, 200, z)
        set_block(lab, corner, "packed_ice")
        set_block(lab, (x, 201, z), "air")
        target_is_start = side in (0, 2)
        direction = (-dx, -dz) if target_is_start else (dx, dz)
        end = 1 if target_is_start else 4
        for offset in range(1, 6):
            at = (x + offset * dx, z + offset * dz)
            set_block(lab, (at[0], 201, at[1]), "air")
            if offset == 5:
                set_block(lab, (at[0], 200, at[1]), "packed_ice")
                set_block(lab, (at[0], 201, at[1]), "oak_sign[waterlogged=false]")
                continue
            pos = (at[0], 200, at[1])
            storage[pos] = 5
            facing = "down" if offset == end else DIRECTIONS[direction]
            set_block(lab, pos, f"hopper[facing={facing}]")
        for offset in ([1] if target_is_start else [4, 5]):
            pos = (x + offset * dx, 199, z + offset * dz)
            storage[pos] = 5
            set_block(lab, pos, f"hopper[facing={DIRECTIONS[direction]}]")
        if side in (0, 2):
            drain = (x, 199, z)
            chest = (x, 198, z)
            storage[drain], storage[chest] = 5, 27
            outputs.add(chest)
            set_block(lab, drain, "hopper[facing=down]")
            set_block(lab, chest, "chest")
            set_block(lab, (x, 202, z), "cobweb")
    for x, z in corners:
        set_block(lab, (x, 201, z), "water")
    return Fixture("water", (35, 201, 3), 12, [(32.5, 202.6, .5), (38.5, 202.6, 6.5)],
                   storage, outputs, {}, "9 x 9 x 5 bounding box, 2 cobweb cells")


def build_carts(lab):
    lab.command("fill 63 198 -1 69 204 1 minecraft:air", "No blocks were filled")
    lab.command(f"kill @e[type={HOPPER},tag=roses_fixture_cart]", "No entity was found")
    storage, outputs, inputs, carts = {}, set(), [], {}
    for x in (64, 68):
        chest, hopper, rail = (x, 199, 0), (x, 200, 0), (x, 201, 0)
        storage[chest], storage[hopper] = 27, 5
        outputs.add(chest)
        set_block(lab, chest, "chest")
        set_block(lab, hopper, "hopper[facing=down]")
        set_block(lab, rail, "powered_rail[powered=false,shape=east_west]")
        require(lab.block(rail)["id"] == "minecraft:powered_rail", "rail will not stay over the hopper")
        for dx, dz in DIRECTIONS:
            set_block(lab, (x + dx, 201, dz), "glass")
        lab.command(f"summon {HOPPER} {x+.5} 201.15 .5 {{Tags:[\"roses_fixture_cart\"]}}")
        inputs.append((x+.5, 202.6, .5))
    found = lab.rpc("entities.query", dimension="minecraft:overworld",
                    center=dict(zip("xyz", (66, 201, 0))), radius=7, types=[HOPPER])
    require(found["total"] == 2, "expected two collection carts")
    for cart in found["entities"]:
        carts[cart["uuid"]] = 5
    return Fixture("carts", (66, 201, 0), 12, inputs, storage, outputs, carts, "7 x 3 x 5 bounding box")


def seed(lab, fixture, payload, age=0):
    target = Counter()
    for pos in fixture.inputs:
        for item, count in payload:
            lab.command(f'summon minecraft:item {xyz(pos)} {{Age:{age}s,Item:{{id:"{item}",count:{count}}}}}')
            target[item] += count
    return target


def scan(lab, fixture, include_filler=False):
    moment = lab.game_time()
    output, buffered, entities = Counter(), Counter(), Counter()
    for pos in fixture.storage:
        group = output if pos in fixture.outputs else buffered
        group.update(totals(lab.inventory(pos)))
    for key in fixture.carts:
        buffered.update(totals(lab.nbt(f"entity {key}").get("Items", [])))
    drops = lab.items(fixture.center, fixture.radius)
    entities.update(totals(item["stack"] for item in drops))
    require(lab.game_time() == moment, "world changed during snapshot")
    item_slots = dict(chests=sum(fixture.storage[pos] for pos in fixture.outputs),
                      hoppers=sum(slots for pos, slots in fixture.storage.items() if pos not in fixture.outputs),
                      carts=sum(fixture.carts.values()))
    result = dict(tick=moment, chests=dict(output), buffered=dict(buffered), loose=dict(entities),
                  drops=drops, capacity_slots=item_slots)
    if not include_filler:
        for group in (result["chests"], result["buffered"], result["loose"]):
            group.pop(FILLER, None)
    return result


def accounted(sample):
    result = Counter()
    for key in ("chests", "buffered", "loose"):
        result.update(sample[key])
    return result


def stock_full(lab, fixture, outputs_only=False):
    containers = [(f"block {xyz(pos)}", slots) for pos, slots in fixture.storage.items()
                  if not outputs_only or pos in fixture.outputs]
    if not outputs_only:
        containers.extend((f"entity {key}", slots) for key, slots in fixture.carts.items())
    for target, count in containers:
        contents = ",".join(f'{{Slot:{slot}b,id:"{FILLER}",count:64}}' for slot in range(count))
        lab.command(f"data merge {target} {{Items:[{contents}]}}")


def clear_storage(lab, fixture):
    for target in [f"block {xyz(pos)}" for pos in fixture.storage] + [
        f"entity {key}" for key in fixture.carts
    ]:
        lab.command(f"data remove {target} Items", "Nothing changed")


def open_trial(lab, fixture):
    target = seed(lab, fixture, PAYLOAD)
    start = lab.game_time()
    samples = []
    for delta in (20, 80, 120, 380, 720, 800):
        lab.sprint(delta)
        sample = scan(lab, fixture)
        sample["elapsed_ticks"] = sample["tick"] - start
        samples.append(sample)
        require(accounted(sample) == target, f"{fixture.name}: missing or extra items after {sample['elapsed_ticks']} ticks")
    require(Counter(samples[-1]["chests"]) == target, f"{fixture.name}: open outputs did not drain")
    return dict(input=dict(target), samples=samples)


def blocked_trial(lab, fixture):
    stock_full(lab, fixture, outputs_only=True)
    target = seed(lab, fixture, PAYLOAD)
    lab.sprint(1000)
    blocked = scan(lab, fixture)
    require(accounted(blocked) == target and Counter(blocked["buffered"]) == target,
            f"{fixture.name}: blocked output failed to hold incoming items in intermediate inventories")
    for output in fixture.outputs:
        lab.command(f"data remove block {xyz(output)} Items")
    lab.sprint(1600)
    recovered = scan(lab, fixture)
    require(Counter(recovered["chests"]) == target and accounted(recovered) == target,
            f"{fixture.name}: incomplete recovery from blocked output")
    return dict(input=dict(target), while_blocked=blocked, after_clear=recovered)


def check_water_loop(lab, fixture):
    lab.command('summon minecraft:item 32.8 201.55 0.5 {Item:{id:"minecraft:diamond",count:1}}')
    path = []
    for _ in range(16):
        lab.sprint(35)
        drops = lab.items(fixture.center, fixture.radius)
        require(len(drops) == 1, "loop probe was lost or duplicated")
        path.append(drops[0])
    sides_seen = sum((
        any(drop["x"] < 32.3 for drop in path),
        any(drop["x"] > 38.7 for drop in path),
        any(drop["z"] < .3 for drop in path),
        any(drop["z"] > 6.7 for drop in path),
    ))
    require(sides_seen == 4 and len({drop["uuid"] for drop in path}) == 1,
            "the same item did not reach all four sides")
    lab.command(f"kill {path[0]['uuid']}")
    return path


def pause_trial(lab, fixture):
    item = "minecraft:cobbled_deepslate"
    inputs = [(int(x), 204, int(z)) for x, _, z in fixture.inputs]
    for pos in inputs:
        x, y, z = pos
        outlet = (1, 0) if x == 32 else (-1, 0)
        for height in (y-1, y-2):
            for dx, dz in DIRECTIONS:
                if fixture.name == "water" and height == y-2 and (dx, dz) == outlet:
                    continue
                set_block(lab, (x+dx, height, z+dz), "glass")
        set_block(lab, pos, "dropper[facing=down]")
        put(lab, pos, 0, item, 5)
    elapsed = lab.sprint(6200)
    paused = [lab.inventory(pos) for pos in inputs]
    require(all(totals(slots) == Counter({item: 5}) for slots in paused)
            and not lab.items(fixture.center, fixture.radius), "paused input escaped into the channel")
    clear_storage(lab, fixture)
    for _ in range(5):
        for x, y, z in inputs:
            set_block(lab, (x+1, y, z), "redstone_block")
        lab.advance(6)
        for x, y, z in inputs:
            set_block(lab, (x+1, y, z), "air")
        lab.advance(6)
    lab.sprint(1000)
    final = scan(lab, fixture)
    require(all(not lab.inventory(pos) for pos in inputs)
            and Counter(final["chests"]) == Counter({item: 10})
            and accounted(final) == Counter({item: 10}), "paused input did not resume exactly")
    return dict(paused_ticks=elapsed, upstream_held=paused, after_resume=final)


def exercise(lab, builder):
    fixture = builder(lab)
    lab.command(f"kill @e[type=minecraft:item,x={fixture.center[0]},y={fixture.center[1]},"
                f"z={fixture.center[2]},distance=..{fixture.radius}]", "No entity was found")
    lab.sprint(120)
    opened = open_trial(lab, fixture)
    clear_storage(lab, fixture)
    blocked = blocked_trial(lab, fixture)

    stock_full(lab, fixture)
    expected_fill = sum(fixture.storage.values()) + sum(fixture.carts.values())
    full = scan(lab, fixture, include_filler=True)
    require(accounted(full) == Counter({FILLER: expected_fill*64}), f"{fixture.name}: incorrect full fixture")
    age_input = seed(lab, fixture, [("minecraft:diamond", 11), ("minecraft:quartz", 17)], age=5_800)
    samples_full = []
    for delta in (20, 40, 80, 80):
        lab.sprint(delta)
        samples_full.append(scan(lab, fixture))
    require(accounted(samples_full[0]) == age_input, f"{fixture.name}: bad blocked-test starting balances")
    require(all(not stage["chests"] and not stage["buffered"] for stage in samples_full),
            f"{fixture.name}: full receiver unexpectedly admitted extra items")
    loop = check_water_loop(lab, fixture) if fixture.name == "water" else []
    pause = pause_trial(lab, fixture)
    no_web = None
    if fixture.name == "water":
        clear_storage(lab, fixture)
        for x, _, z in fixture.inputs:
            set_block(lab, (int(x), 202, int(z)), "air")
        no_web = open_trial(lab, fixture)
    return dict(name=fixture.name, footprint=fixture.footprint, open=opened,
                output_blocked=blocked, full_input=dict(age_input), full_samples=samples_full,
                full_despawned=dict(age_input-accounted(samples_full[-1])),
                physical_loop_probe=loop, pause=pause, water_without_cobweb=no_web)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("server", type=Path, nargs="?", default=Path(__file__).with_name("server"))
    args = parser.parse_args()
    lab = Lab(args.server)
    lab.command("forceload add 16 -16 79 15", "No chunks were marked")
    time.sleep(2)
    try:
        lab.command("tick freeze")
        for builder in (build_water, build_carts):
            report = exercise(lab, builder)
            Path(__file__).with_name(f"buffer-{report['name']}-report.json").write_text(json.dumps(report, indent=2))
            print(f"{report['name']}: open and full trials recorded", flush=True)
    finally:
        lab.command("tick unfreeze")
        lab.command("forceload remove 16 -16 79 15")


if __name__ == "__main__":
    main()
