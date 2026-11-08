param(
    [Parameter(Mandatory=$true)][string]$OriginalCsv,
    [Parameter(Mandatory=$true)][string]$DataverseMetadata,
    [Parameter(Mandatory=$true)][ValidateSet('primary','verify')][string]$Trial
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$original = (Resolve-Path -LiteralPath $OriginalCsv).Path
$metadata = (Resolve-Path -LiteralPath $DataverseMetadata).Path
$local = (Resolve-Path -LiteralPath '.morpheus/aqsol-v2').Path
$parent = Get-Content -Raw -LiteralPath 'lab/protocols/aqsol-solubility-v1.json' | ConvertFrom-Json
if (@(@($original, $metadata, $local) | Where-Object { $_.Contains(',') }).Count) {
    throw 'An AqSolDB mount path contains a comma'
}
if ((Get-Item -LiteralPath $original).Length -ne $parent.source.original_bytes -or
    (Get-FileHash -Algorithm SHA256 -LiteralPath $original).Hash -ne $parent.source.sha256) {
    throw 'The local original AqSolDB file does not match V1'
}
$image = $parent.execution.image
if ($image -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Invalid pinned image ID' }
$files = @('lab.py','iris_pilot.py','aqsol_pilot.py','aqsol-requirements.txt','aqsol-linux-amd64.lock',
    'aqsol_v2.py','protocols/aqsol-solubility-v1.json','protocols/aqsol-solubility-v2.json',
    'evidence/aqsol-v1-preflight-blocked.json')
$tracked = @($files | ForEach-Object { "lab/$_" }) + @('lab/aqsol_v2_docker.ps1','lab/registry.jsonl')
git ls-files --error-unmatch -- $tracked | Out-Null
if ($LASTEXITCODE) { throw 'Protocol, code, inputs and dependency lock must be committed' }
git diff --quiet HEAD -- $tracked
if ($LASTEXITCODE) { throw 'Protocol or sources differ from the frozen commit' }
$bundle = Join-Path $local "bundle-$Trial"
New-Item -ItemType Directory -Path $bundle | Out-Null
foreach ($file in $files) {
    $target = Join-Path $bundle $file
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination $target
}
$docker = (Get-Command docker.exe).Source
$engine = @('--host', 'npipe:////./pipe/dockerDesktopLinuxEngine')
$deps = 'morpheus-mr022-aqsol-deps-v1'
$labels = & $docker @engine volume inspect $deps --format '{{json .Labels}}'
if ($LASTEXITCODE -or ($labels | ConvertFrom-Json).'morpheus.scope' -ne 'mr022-dependencies') {
    throw 'Missing verified V1 dependency volume'
}
$limits = @('run','--rm','--pull=never','--network=none','--read-only','--user','65534:65534',
    '--cap-drop=ALL','--security-opt=no-new-privileges','--memory=768m','--memory-swap=768m',
    '--cpus=1','--pids-limit=48','--ipc=private','--shm-size=4m','--ulimit','cpu=120:125',
    '--env','OMP_NUM_THREADS=1','--env','OPENBLAS_NUM_THREADS=1','--env','PYTHONPATH=/deps')
$mounts = @('--mount', "type=bind,source=$bundle,target=/pilot,readonly",
    '--mount', "type=volume,source=$deps,target=/deps,readonly",
    '--mount', "type=bind,source=$original,target=/input.csv,readonly",
    '--mount', "type=bind,source=$metadata,target=/metadata.json,readonly")
& $docker @engine @limits @mounts $image python -B /pilot/aqsol_v2.py /input.csv /metadata.json
exit $LASTEXITCODE
