param(
    [Parameter(Mandatory=$true)][ValidateSet('Test','Run','Resume')][string]$Phase,
    [string]$OriginalCsv,
    [string]$DataverseMetadata
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
$reviewed = '5024da581fa27fcb5793b676a004d5d9c1f77172'
$runner = @('aqsol_v2_go.py','test_aqsol_v2_go.py','aqsol_v2_go.ps1')
$base = @('lab.py','iris_pilot.py','aqsol_pilot.py','aqsol_model.py','aqsol_v2.py',
    'aqsol-requirements.txt','aqsol-linux-amd64.lock','protocols/aqsol-solubility-v1.json',
    'protocols/aqsol-solubility-v2.json','evidence/aqsol-v2-preflight.json')
$testInputs = @('test_aqsol_pilot.py','test_aqsol_model.py','test_aqsol_v2.py')
$trackedBase = @(($base + $testInputs) | ForEach-Object { "lab/$_" })
$trackedRunner = @($runner | ForEach-Object { "lab/$_" })
git ls-files --error-unmatch -- $trackedBase $trackedRunner | Out-Null
if ($LASTEXITCODE) { throw 'Inputs and executor must be committed' }
git diff --quiet $reviewed HEAD -- $trackedBase
if ($LASTEXITCODE) { throw 'Reviewed inputs or executable components changed' }
git diff --quiet HEAD -- $trackedBase $trackedRunner
if ($LASTEXITCODE) { throw 'Frozen inputs or executor have local changes' }
$freeze = git log -1 --format='%H' -- $trackedRunner
if ($LASTEXITCODE -or $freeze -notmatch '^[a-f0-9]{40}$') { throw 'Missing executor freeze' }
git merge-base --is-ancestor $reviewed $freeze
if ($LASTEXITCODE) { throw 'Executor freeze must descend from reviewed main' }
$parent = Get-Content -Raw -LiteralPath 'lab/protocols/aqsol-solubility-v1.json' | ConvertFrom-Json
$image = $parent.execution.image
if ($image -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Invalid frozen image' }
$local = (Resolve-Path -LiteralPath '.morpheus/aqsol-v2-run').Path
$runRoot = Join-Path (Split-Path -Parent $repo) '.morpheus/mr022-v2-go-run'
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
if ((Get-Item -LiteralPath $runRoot).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'Run root must be a real directory'
}
$state = Join-Path $runRoot 'checkpoint'
$testPass = Join-Path $runRoot 'synthetic-pass.txt'
$intent = Join-Path $runRoot 'launch.intent.json'
$bundle = Join-Path $local ([guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $bundle | Out-Null
$files = $base + @('aqsol_v2_go.py')
if ($Phase -eq 'Test') {
    $files += $testInputs + @('test_aqsol_v2_go.py')
}
foreach ($file in $files) {
    $target = Join-Path $bundle $file
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination $target
}
$docker = (Get-Command docker.exe).Source
$engine = @('--host','npipe:////./pipe/dockerDesktopLinuxEngine')
$deps = 'morpheus-mr022-aqsol-deps-v1'
$labels = & $docker @engine volume inspect $deps --format '{{json .Labels}}'
if ($LASTEXITCODE -or ($labels | ConvertFrom-Json).'morpheus.scope' -ne 'mr022-dependencies') {
    throw 'The pinned V1 dependency volume is unavailable'
}
$limits = @('run','--rm','--pull=never','--network=none','--read-only','--user','65534:65534',
    '--cap-drop=ALL','--security-opt=no-new-privileges','--memory=768m','--memory-swap=768m',
    '--cpus=1','--pids-limit=48','--ipc=private','--shm-size=4m','--ulimit','cpu=240:250',
    '--tmpfs','/tmp:rw,noexec,nosuid,size=64m,mode=1777','--workdir','/tmp',
    '--env','OMP_NUM_THREADS=1','--env','OPENBLAS_NUM_THREADS=1','--env','MKL_NUM_THREADS=1','--env','PYTHONPATH=/deps')
$mounts = @('--mount',"type=bind,source=$bundle,target=/pilot,readonly",
    '--mount',"type=volume,source=$deps,target=/deps,readonly")
if ($Phase -eq 'Test') {
    & $docker @engine @limits @mounts $image python -B -m unittest discover -s /pilot -p 'test_aqsol*.py' -v
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    [IO.File]::WriteAllText($testPass,$freeze)
    exit 0
}
if ((Get-Content -Raw -LiteralPath $testPass).Trim() -ne $freeze) { throw 'Offline synthetic tests are required on this freeze' }
$original = (Resolve-Path -LiteralPath $OriginalCsv).Path
$metadata = (Resolve-Path -LiteralPath $DataverseMetadata).Path
if (@(@($original,$metadata,$bundle,$state) | Where-Object { $_.Contains(',') }).Count) {
    throw 'AqSolDB mount path contains a comma'
}
if ((Get-Item -LiteralPath $original).Length -ne $parent.source.original_bytes -or
    (Get-FileHash -Algorithm SHA256 -LiteralPath $original).Hash -ne $parent.source.sha256) {
    throw 'The source bytes do not match the approved V2 source'
}
$name = 'morpheus-mr022-v2-go-run'
$existing = @(& $docker @engine container ls --all --filter "name=^/$name$" --format '{{.Names}}')
if ($LASTEXITCODE -or $existing.Count) { throw 'Previous container outcome must be reconciled before proceeding' }
if ($Phase -eq 'Run') {
    if (Test-Path -LiteralPath $state) { throw 'A prior checkpoint exists. Reconcile and use Resume.' }
    $record = @{freeze=$freeze; started_utc=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json -Compress
    $file = [IO.File]::Open($intent,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($record)
        $file.Write($bytes,0,$bytes.Length)
        $file.Flush($true)
    } finally { $file.Dispose() }
    New-Item -ItemType Directory -Path $state | Out-Null
} elseif ((Get-Content -Raw -LiteralPath $intent | ConvertFrom-Json).freeze -ne $freeze -or
    !(Test-Path -LiteralPath (Join-Path $state 'evidence.sqlite3') -PathType Leaf) -or
    !(Test-Path -LiteralPath (Join-Path $state 'worker.sqlite3') -PathType Leaf)) {
    throw 'Uncertain or missing prior checkpoint. Do not start another fit.'
}
if ((Get-Item -LiteralPath $state).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'Checkpoint mount must be a real directory'
}
& $docker @engine @limits @mounts --name $name --mount "type=bind,source=$original,target=/input.csv,readonly" --mount "type=bind,source=$metadata,target=/metadata.json,readonly" --mount "type=bind,source=$state,target=/state" $image python -B /pilot/aqsol_v2_go.py /input.csv /metadata.json /state $freeze
exit $LASTEXITCODE
