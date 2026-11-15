"""Inspect and test the disposable ROSES fixture world using MCPFabric."""

import argparse
from collections import Counter
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

import nbtlib


class Lab:
    def __init__(self, server):
        settings = dict(
            line.split("=", 1)
            for line in (server / "server.properties").read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
        config = json.loads((server / "config/mcpfabric.config.json").read_text())
        if (settings.get("level-name"), settings.get("server-ip"), settings.get("server-port")) != (
            "fixture-world", "127.0.0.1", "25580"
        ) or not config["requireAuth"] or config["host"] != "127.0.0.1":
            raise ValueError("Expected the authenticated, loopback-only ROSES fixture server")
        self.url = f"http://127.0.0.1:{config['port']}/rpc"
        self.token = config["token"]

    def rpc(self, method, **params):
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        request = Request(self.url, payload, {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        })
        with urlopen(request, timeout=12) as response:
            data = json.load(response)
        if "error" in data:
            raise RuntimeError(f"{method}: {data['error']}")
        return data["result"]

    def command(self, command, expected_failure=None):
        result = self.rpc("command.run", command=command)
        output = result["output"]
        if not result["success"] and not (
            expected_failure and any(expected_failure in line for line in output)
        ):
            raise RuntimeError(f"{command}: {output}")
        return output

    def block(self, pos):
        return self.rpc("world.getBlock", dimension="minecraft:overworld", **dict(zip("xyz", pos)))

    def nbt(self, target):
        output = self.command(f"data get {target}")
        return nbtlib.parse_nbt(output[-1].split(": ", 1)[1]).unpack()

    def inventory(self, pos):
        return self.nbt(f"block {xyz(pos)}").get("Items", [])

    def items(self, center, radius):
        result = self.rpc("entities.query", dimension="minecraft:overworld", center=dict(zip("xyz", center)),
                          radius=radius, types=["minecraft:item"])
        if result["returned"] != result["total"]:
            raise RuntimeError("Dropped-item scan was truncated")
        return [{**item, "stack": self.nbt(f"entity {item['uuid']} Item")} for item in result["entities"]]

    def advance(self, ticks):
        before = self.game_time()
        self.command(f"tick step {ticks}")
        deadline = time.monotonic() + max(15, ticks / 10)
        while (elapsed := self.game_time() - before) < ticks and time.monotonic() < deadline:
            time.sleep(0.1)
        if elapsed != ticks:
            raise RuntimeError(f"Expected {ticks} ticks, observed {elapsed}")

    def sprint(self, ticks):
        before = self.game_time()
        self.command(f"tick sprint {ticks}")
        deadline = time.monotonic() + 240
        while (elapsed := self.game_time() - before) < ticks and time.monotonic() < deadline:
            time.sleep(0.2)
        if not ticks <= elapsed <= ticks + 2:
            raise RuntimeError(f"Expected a sprint of {ticks} ticks, observed {elapsed}")
        return elapsed

    def game_time(self):
        result = self.rpc("command.run", command="time query gametime")
        if not result["success"]:
            raise RuntimeError(result["output"])
        return result["resultValue"]


def xyz(pos):
    return " ".join(str(value) for value in pos)


def totals(stacks):
    counts = Counter()
    for stack in stacks:
        counts[stack["id"]] += stack["count"]
    return counts


SOURCE = (0, 203, -1)
INLET = (0, 202, -1)
TRANSPORT = (0, 202, 0)
FILTER = (0, 201, 0)
OUTLET = (0, 200, 0)
BUFFER = (0, 199, 0)
SORTED = (0, 198, 0)
BYPASS = (1, 202, 0)
CONTAINERS = dict(source=SOURCE, inlet=INLET, transport=TRANSPORT, filter=FILTER,
                  outlet=OUTLET, buffer=BUFFER, sorted=SORTED, bypass=BYPASS)
WATCHED = dict(filter=FILTER, outlet=OUTLET, comparator=(0, 201, 1), wire=(1, 200, 1),
               gate=(1, 200, 0))
TARGET = "minecraft:cobbled_deepslate"
FILLER = 'minecraft:stick[custom_name="Sorter filler"]'
BASELINE = Counter({TARGET: 41, "minecraft:stick": 4})


def snapshot(lab):
    sample = {
        "tick": lab.game_time(),
        "blocks": {name: lab.block(pos) for name, pos in WATCHED.items()},
        "inventories": {name: lab.inventory(pos) for name, pos in CONTAINERS.items()},
        "dropped": lab.items((0, 200, 2), 12),
    }
    require(sample["tick"] == lab.game_time(), "simulation advanced during snapshot")
    return sample


def conservation(sample):
    counts = totals(item for slots in sample["inventories"].values() for item in slots)
    counts.update(totals(item["stack"] for item in sample["dropped"]))
    return counts


def place(lab, pos, block):
    lab.command(f"setblock {xyz(pos)} {block}", "Could not set the block")


def put(lab, pos, slot, item, count=1):
    lab.command(f"item replace block {xyz(pos)} container.{slot} with {item} {count}")


def reset_sorter(lab):
    lab.command("fill -2 197 -2 4 204 6 minecraft:air", "No blocks were filled")
    lab.command("kill @e[type=minecraft:item,x=0,y=200,z=2,distance=..12]", "No entity was found")
    lab.command("fill -2 197 -2 4 197 6 minecraft:smooth_stone")
    for pos, block in {
        SORTED: "chest", BYPASS: "chest", SOURCE: "chest", BUFFER: "hopper[facing=down]",
        (-1, 201, 0): "smooth_stone", OUTLET: "hopper[facing=down]",
        FILTER: "hopper[facing=west]", TRANSPORT: "hopper[facing=east]",
        INLET: "hopper[facing=south]", (0, 201, 1): "comparator[facing=north]",
        (0, 200, 1): "smooth_stone", (0, 200, 2): "smooth_stone",
        (1, 200, 2): "smooth_stone", (1, 199, 1): "smooth_stone",
        (1, 199, 0): "smooth_stone", (2, 200, 0): "water_cauldron[level=1]",
        (1, 200, 0): "comparator[facing=east,mode=subtract]",
    }.items():
        place(lab, pos, "minecraft:" + block)
    for pos, directions in {
        (0, 201, 2): "east=side,south=none,north=side,west=none",
        (1, 201, 2): "east=none,south=none,north=side,west=side",
        (1, 200, 1): "east=none,south=up,north=side,west=none",
    }.items():
        place(lab, pos, f"minecraft:redstone_wire[{directions}]")
    # The comparator needs time to settle before it takes over the lock.
    setup_lock = (0, 200, -1)
    place(lab, setup_lock, "minecraft:redstone_block")
    put(lab, FILTER, 0, TARGET, 41)
    for slot in range(1, 5):
        put(lab, FILTER, slot, FILLER)
    lab.advance(32)
    place(lab, setup_lock, "minecraft:air")
    lab.advance(32)
    idle = snapshot(lab)
    require(idle["blocks"]["outlet"]["properties"]["enabled"] == "false", "idle outlet must be locked")
    require(totals(idle["inventories"]["filter"]) == BASELINE, "filter lost reserve during fixture setup")
    require(conservation(idle) == BASELINE, f"unexpected initial items: {conservation(idle)}")


def require(condition, reason):
    if not condition:
        raise AssertionError(reason)


def test_blocked_sorter(lab):
    reset_sorter(lab)
    blocker = "minecraft:cobblestone"
    contents = Counter({blocker: 27 * 64})
    expected = Counter({TARGET: 48, "minecraft:dirt": 5})
    for slot in range(27):
        put(lab, SORTED, slot, blocker, 64)
    for slot, (item, count) in enumerate(expected.items()):
        put(lab, SOURCE, slot, item, count)
    initial = snapshot(lab)
    require(conservation(initial) == BASELINE + expected + contents, "blocked fixture loaded wrong quantities")
    lab.sprint(1000)
    blocked = snapshot(lab)
    require(totals(blocked["inventories"]["sorted"]) == contents, "blocked chest changed unexpectedly")
    require(conservation(blocked) == BASELINE + expected + contents, "blocked case lost or duplicated items")
    require(not blocked["dropped"], "blocked sorter ejected loose items")
    lab.command(f"data remove block {xyz(SORTED)} Items")
    lab.sprint(1000)
    final = snapshot(lab)
    require(conservation(final) + contents == BASELINE + expected + contents,
            "recovery lost or duplicated items after accounting for removed blockers")
    require(totals(final["inventories"]["sorted"]) == Counter({TARGET: 48}), "recovery misrouted deepslate")
    require(totals(final["inventories"]["bypass"]) == Counter({"minecraft:dirt": 5}), "recovery misrouted dirt")
    require(totals(final["inventories"]["filter"]) == BASELINE, "recovery drained filter stock")
    require(not final["dropped"] and all(not final["inventories"][name] for name in ("source", "inlet", "transport", "outlet", "buffer")),
            "recovery stranded items")
    return {"case": "blocked-then-cleared", "input": dict(expected), "initial": initial, "initial_blockers": dict(contents),
            "removed_blockers": dict(contents), "while_blocked": blocked, "final": final}


def test_sorter(lab):
    lab.command("forceload add -16 -16 15 15", "No chunks were marked")
    try:
        lab.command("tick freeze")
        cases = [
            ("mixed", {TARGET: 64, "minecraft:dirt": 19, "minecraft:iron_sword": 1}),
            ("partial", {TARGET: 17, "minecraft:gravel": 7}),
        ]
        reports = []
        for name, expected in cases:
            reset_sorter(lab)
            for slot, (item, count) in enumerate(expected.items()):
                put(lab, SOURCE, slot, item, count)
            lab.advance(24)
            running = snapshot(lab)
            lab.advance(sum(expected.values()) * 16 + 80)
            final = snapshot(lab)
            initial = BASELINE + Counter(expected)
            require(conservation(running) == initial, f"{name}: items missing or duplicated mid-run")
            require(conservation(final) == initial, f"{name}: items missing or duplicated")
            require(totals(final["inventories"]["sorted"]) == Counter({TARGET: expected[TARGET]}),
                    f"{name}: wrong sorted output")
            require(totals(final["inventories"]["bypass"]) == Counter({k: v for k, v in expected.items() if k != TARGET}),
                    f"{name}: wrong bypass output")
            require(totals(final["inventories"]["filter"]) == BASELINE, f"{name}: changed filter")
            require(not final["dropped"] and all(not final["inventories"][name] for name in ("source", "inlet", "transport", "outlet", "buffer")),
                    f"{name}: residual items")
            reports.append({"case": name, "input": expected, "running": running, "final": final})
        reports.append(test_blocked_sorter(lab))
        return reports
    finally:
        lab.command("tick unfreeze")
        lab.command("forceload remove -16 -16 15 15")


def test_shulker(lab):
    box = (10, 201, 0)
    dispenser = (9, 201, 0)
    extractor = (10, 200, 0)
    buffer = (10, 199, 0)
    left_chest = (10, 198, 0)
    right_chest = (11, 198, 0)
    hopper_lock = (10, 200, -1)
    piston_power = (12, 201, 0)
    target_count = 27 * 64

    def output():
        return totals(lab.inventory(left_chest) + lab.inventory(right_chest))

    lab.command("forceload add 0 -16 15 15", "No chunks were marked")
    try:
        lab.command("tick freeze")
        lab.command("fill 8 197 -2 14 203 2 minecraft:air", "No blocks were filled")
        lab.command("kill @e[type=minecraft:item,x=10,y=200,z=0,distance=..5]", "No entity was found")
        for pos, block in {
            left_chest: "chest[facing=north,type=left]", right_chest: "chest[facing=north,type=right]",
            buffer: "hopper[facing=down]", extractor: "hopper[facing=down]",
            dispenser: "dispenser[facing=east]", (11, 201, 0): "piston[facing=west]",
            (10, 201, -1): "glass", (10, 201, 1): "glass",
        }.items():
            place(lab, pos, "minecraft:" + block)

        # Lock extraction while the dispenser places the filled box.
        place(lab, hopper_lock, "minecraft:redstone_block")
        slots = ",".join(f'{{slot:{slot},item:{{id:"{TARGET}",count:64}}}}' for slot in range(27))
        put(lab, dispenser, 0, f"minecraft:shulker_box[minecraft:container=[{slots}]]")
        place(lab, (9, 202, 0), "minecraft:redstone_block")
        lab.advance(12)
        require(lab.block(box)["id"] == "minecraft:shulker_box", "dispenser did not place the shulker")
        require(not lab.inventory(dispenser), "dispenser kept the shulker")
        require(totals(lab.inventory(box)) == Counter({TARGET: target_count}), "wrong initial shulker payload")
        place(lab, hopper_lock, "minecraft:air")
        lab.advance(80)
        running = {"box": lab.inventory(box), "extractor": lab.inventory(extractor),
                   "buffer": lab.inventory(buffer), "output": dict(output())}
        require(0 < sum(running["output"].values()) < target_count, "expected an active transfer")
        elapsed = lab.sprint(14_500)
        require(not lab.inventory(box) and not lab.inventory(extractor) and not lab.inventory(buffer),
                "unloader still holds items before empty-box recovery")
        require(output() == Counter({TARGET: target_count}), "missing or extra output items")

        # Isolate and observe the dropped empty box before the hopper retrieves it.
        place(lab, hopper_lock, "minecraft:redstone_block")
        place(lab, piston_power, "minecraft:redstone_block")
        lab.advance(4)
        drops = lab.items(box, 3)
        require(totals(item["stack"] for item in drops) == Counter({"minecraft:shulker_box": 1}),
                "piston did not release exactly one shulker")
        require(not drops[0]["stack"].get("components", {}).get("minecraft:container"),
                "released shulker still contains items")
        place(lab, piston_power, "minecraft:air")
        place(lab, hopper_lock, "minecraft:air")
        lab.advance(120)
        expected = Counter({TARGET: target_count, "minecraft:shulker_box": 1})
        require(output() == expected and not lab.items(box, 3),
                f"empty shulker was not recovered; first drop={drops[0]}, output={output()}")
        return {"input_stacks": 27, "input_items": target_count, "sprint_ticks": elapsed,
                "running": running, "dropped_empty_box": drops[0], "output": dict(output())}
    finally:
        lab.command("tick unfreeze")
        lab.command("forceload remove 0 -16 15 15")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("server", type=Path, help="Disposable ROSES fixture server folder")
    sub = parser.add_subparsers(dest="mode", required=True)
    block = sub.add_parser("block")
    block.add_argument("pos", type=int, nargs=3)
    inventory = sub.add_parser("inventory")
    inventory.add_argument("pos", type=int, nargs=3)
    items = sub.add_parser("items")
    items.add_argument("center", type=int, nargs=3)
    items.add_argument("radius", type=int)
    sub.add_parser("sorter")
    sub.add_parser("shulker")
    args = parser.parse_args()
    lab = Lab(args.server)
    if args.mode == "block":
        print(json.dumps(lab.block(args.pos), indent=2))
    elif args.mode == "inventory":
        print(json.dumps(lab.inventory(args.pos), indent=2))
    elif args.mode == "items":
        print(json.dumps(lab.items(args.center, args.radius), indent=2))
    elif args.mode == "sorter":
        print(json.dumps(test_sorter(lab), indent=2))
    else:
        print(json.dumps(test_shulker(lab), indent=2))


if __name__ == "__main__":
    main()
