"""Build vanilla structure templates from the three downloaded single-region schematics."""

import argparse
from collections import Counter
from copy import deepcopy
from math import floor
from pathlib import Path

import nbtlib as nbt


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", type=Path, help="Directory with BU002, BU008 and BU010 litematic files")
parser.add_argument("server", type=Path, help="Disposable mechanism server")
args = parser.parse_args()
assert "level-name=fixture-world" in (args.server / "server.properties").read_text().splitlines()
out = args.server / "fixture-world/generated/roses/structure"
out.mkdir(parents=True, exist_ok=True)
axes = "xyz"

for path in sorted(args.source.glob("BU*.litematic")):
    litematic = nbt.load(path)
    assert len(litematic["Regions"]) == 1
    region = next(iter(litematic["Regions"].values()))
    sx, sy, sz = [int(region["Size"][axis]) for axis in axes]
    assert min(sx, sy, sz) > 0
    palette = region["BlockStatePalette"]
    words = [int(value) & ((1 << 64) - 1) for value in region["BlockStates"]]
    bits = max(2, (len(palette) - 1).bit_length())
    positions = {tuple(int(t[axis]) for axis in axes): t for t in region.get("TileEntities", [])}
    blocks = []
    counts = Counter()
    for number in range(sx * sy * sz):
        bit = number * bits
        word = bit // 64
        value = words[word] | (words[word + 1] << 64 if word + 1 < len(words) else 0)
        state = (value >> (bit % 64)) & ((1 << bits) - 1)
        x, y, z = number % sx, number // (sx * sz), (number // sx) % sz
        name = str(palette[state]["Name"])
        if name in {"minecraft:air", "minecraft:structure_void"}:
            continue
        counts[name] += 1
        block = nbt.Compound(pos=nbt.List[nbt.Int]([x, y, z]), state=nbt.Int(state))
        if (x, y, z) in positions:
            tag = deepcopy(positions[(x, y, z)])
            for axis in axes:
                tag.pop(axis, None)
            block["nbt"] = tag
        blocks.append(block)
    entities = []
    for entity in region.get("Entities", []):
        tag = deepcopy(entity)
        pos = tag["Pos"]
        assert all(0 <= float(p) <= limit for p, limit in zip(pos, (sx, sy, sz)))
        tag.pop("UUID", None)
        entities.append(nbt.Compound(pos=pos, blockPos=nbt.List[nbt.Int]([floor(p) for p in pos]), nbt=tag))
    template = nbt.File({
        "DataVersion": litematic["MinecraftDataVersion"],
        "size": nbt.List[nbt.Int]([sx, sy, sz]),
        "palette": palette,
        "blocks": nbt.List[nbt.Compound](blocks),
        "entities": nbt.List[nbt.Compound](entities),
    }, gzipped=True)
    template.save(out / f"{path.stem.lower()}.nbt")
    print(path.stem, "size", (sx, sy, sz), "blocks", len(blocks), "entities", len(entities), counts)
