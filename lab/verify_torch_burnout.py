import argparse
import json
from pathlib import Path
sys.path.insert(0,"work/mechanisms")
from mechanism_lab import *
parser = argparse.ArgumentParser(description="Reproduce the old sorter gate's torch burnout on the fixture server")
parser.add_argument("server", type=Path, nargs="?", default=Path(__file__).with_name("server"))
lab=Lab(parser.parse_args().server)
lab.command("forceload add -16 -16 15 15","No chunks were marked")
try:
 lab.command("tick freeze")
 reset_sorter(lab)
 support, torch, pulse = (1,200,1), (1,200,0), (2,201,1)
 place(lab, support, "minecraft:smooth_stone")
 place(lab, torch, "minecraft:redstone_wall_torch[facing=north]")
 place(lab, (1,201,1), "minecraft:redstone_wire[east=side,west=side]")
 lab.advance(12)
 require(lab.block(torch)["properties"]["lit"]=="true","fixture torch did not light")
 samples=[]
 for cycle in range(8):
  place(lab,pulse,"minecraft:redstone_block")
  lab.advance(4)
  off=lab.block(torch)["properties"]["lit"]=="false"
  place(lab,pulse,"minecraft:air")
  lab.advance(4)
  samples.append(dict(cycle=cycle+1,powered_phase_turned_off=off,unpowered_phase_recovered=lab.block(torch)["properties"]["lit"]=="true"))
 reserve=totals(lab.inventory(FILTER))[TARGET]
 lab.advance(80)
 still_off=lab.block(torch)["properties"]["lit"]=="false"
 drained=reserve-totals(lab.inventory(FILTER))[TARGET]
 lab.advance(110)
 recovered=lab.block(torch)["properties"]["lit"]=="true"
 assert all(s["powered_phase_turned_off"] for s in samples)
 assert all(s["unpowered_phase_recovered"] for s in samples[:7]) and not samples[-1]["unpowered_phase_recovered"]
 assert still_off and drained > 0 and recovered
 print(json.dumps(dict(samples=samples,still_off_after_80_ticks=still_off,reserve_drain_over_80_ticks=drained,recovered_after_cooldown=recovered),indent=2))
finally:
 reset_sorter(lab)
 lab.command("tick unfreeze")
 lab.command("forceload remove -16 -16 15 15")
