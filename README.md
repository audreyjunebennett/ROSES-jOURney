# ROSES tools

Source for the ROSES Minecraft Java 26.3 Fabric Creative bridge and disposable mechanism tests.

## Creative bridge

The bridge uses Worlds to switch the player profile, inventory and game mode. It gates Axiom by Creative dimension and stores a per-player Survival return point. Version 0.3.0 is the source for the build deployed with Axiom 6.1.5, Worlds 2.0.0+26.3, LuckPerms 5.5.85 and Fabric API 0.165.2+26.3. The bridge is server-side.

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
