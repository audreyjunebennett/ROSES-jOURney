# ROSES tools

Source for the ROSES Minecraft Java 26.3 Fabric Creative bridge and disposable mechanism tests.

## Creative bridge

The bridge uses Worlds to switch the player profile, inventory and game mode. It controls Axiom access and stores a per-player Survival return point. It runs on the server with Axiom 6.1.5, Worlds 2.0.0+26.3, LuckPerms 5.5.85 and Fabric API 0.165.2+26.3.

Version 0.3.2 targets Expansive Fantasy Survival at `roses:expansive_fantasy`. It keeps the original `roses:creative` dimension eligible for Axiom and return travel. An entry command waits for the destination's Worlds readiness signal, so Distant Horizons receives the level load event before the player arrives. The scenic round trip and restart were verified on disposable ROSES copies.

Version 0.3.3 adds `/roses axiom on` and `/roses axiom off`. Axiom starts off in Survival on each connection. Players with the LuckPerms node `roses.axiom.survival` can opt in from the Survival group. Opting in enables editing and Axiom's existing Creative auto-switch for that player. Opting out in Survival restores the game mode the player had when opting in. The two ROSES Creative worlds keep their existing Axiom behavior.

Grant the node from the server console with `lp user <player> permission set roses.axiom.survival true`. To roll back, restore the previous bridge JAR and optionally remove the node with `lp user <player> permission unset roses.axiom.survival`.

With a Java 25 JDK on PATH, point the build at an initialized, disposable ROSES 26.3 server copy.

```powershell
.\bridge\build.ps1 -ServerDir '<disposable server directory>'
```

The JAR lands in `bridge/build`. Verify any update in staging and keep a copy of the previous bridge JAR for rollback.

## Mechanism lab

Use the disposable ROSES fixture server. The scripts require Python, `nbtlib` and MCPFabric 0.10.0+26.3 on the fixture server. Configure MCPFabric on authenticated loopback with command execution enabled and discovery and player control off. Keep the fixture server on `127.0.0.1:25580` with `level-name=fixture-world`. Run each fixture separately because they freeze and step the simulation.

```powershell
python lab/mechanism_lab.py '<fixture server>' sorter
python lab/mechanism_lab.py '<fixture server>' shulker
python lab/buffer_experiment.py '<fixture server>'
python lab/verify_torch_burnout.py '<fixture server>'
```

For the published unloader comparison, download the original BU002, BU008 and BU010 Litematica attachments from the [Minecraft Storage Catalog](https://storagecatalog.org/archives/). Name them `BU002.litematic`, `BU008.litematic` and `BU010.litematic`.

```powershell
python lab/inspect_templates.py '<schematic folder>' '<fixture server>'
python lab/published_unloaders.py '<fixture server>' bu010 bu002 bu008
```

Use the prepared hidden-desktop Minecraft Test Lab for graphical checks. Store world backups and generated test reports separately from the source repo.
