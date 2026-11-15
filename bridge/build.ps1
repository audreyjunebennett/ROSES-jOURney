param(
    [Parameter(Mandatory)]
    [string]$ServerDir
)

$ErrorActionPreference = 'Stop'
$server = (Resolve-Path -LiteralPath $ServerDir).Path
$source = Join-Path $PSScriptRoot 'src'
$build = Join-Path $PSScriptRoot 'build'
$classes = Join-Path $build 'classes'
New-Item -ItemType Directory -Path $build, $classes -Force | Out-Null

$api = @(Get-ChildItem -LiteralPath "$server/mods" -Filter 'fabric-api-*.jar' -File)
if ($api.Count -ne 1) { throw 'Expected one Fabric API bundle in the server copy.' }

Push-Location $build
try {
    & jar xf $api[0].FullName META-INF/jars
    if ($LASTEXITCODE -ne 0) { throw 'Fabric API extraction failed.' }
} finally {
    Pop-Location
}

$classpath = @((Get-Item -LiteralPath "$server/versions/26.3/server-26.3.jar").FullName)
$classpath += (Get-ChildItem -LiteralPath "$server/libraries" -Recurse -Filter '*.jar' -File).FullName
$classpath += (Get-ChildItem -LiteralPath "$server/mods" -Filter '*.jar' -File).FullName
$classpath += (Get-ChildItem -LiteralPath "$build/META-INF/jars" -Filter '*.jar' -File).FullName

# javac argument files avoid the Windows command-line length limit.
$argsFile = Join-Path $build 'javac.txt'
$quote = { param([string]$value) '"' + $value.Replace('\', '/') + '"' }
$arguments = @('-cp', (& $quote ($classpath -join ';')), '-d', (& $quote $classes))
$arguments += Get-ChildItem -LiteralPath $source -Filter '*.java' -File | ForEach-Object { & $quote $_.FullName }
$arguments | Set-Content -LiteralPath $argsFile -Encoding utf8NoBOM
& javac "@$argsFile"
if ($LASTEXITCODE -ne 0) { throw 'Bridge compilation failed.' }

$metadata = Get-Content -LiteralPath "$source/fabric.mod.json" -Raw | ConvertFrom-Json
$jar = Join-Path $build "roses-axiom-gate-$($metadata.version).jar"
& jar --create --file $jar -C $classes . -C $source fabric.mod.json -C $source roses_axiom_gate.mixins.json
if ($LASTEXITCODE -ne 0) { throw 'Bridge packaging failed.' }
Write-Output $jar
