param([Parameter(Mandatory=$true)][ValidateSet('setup','test','prepare','preflight','run')][string]$Phase)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
$local = (Resolve-Path -LiteralPath '.morpheus/aqsol-v1').Path
if ($local.Contains(',')) { throw 'AqSolDB mount path contains a comma' }
$docker = (Get-Command docker.exe).Source
$image = (Get-Content -Raw -LiteralPath 'lab/protocols/aqsol-solubility-v1.json' | ConvertFrom-Json).execution.image
if ($image -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Invalid pinned image ID' }
$engine = @('--host', 'npipe:////./pipe/dockerDesktopLinuxEngine')
$limits = @('run', '--rm', '--pull=never', '--network=none', '--read-only', '--user', '65534:65534',
    '--cap-drop=ALL', '--security-opt=no-new-privileges', '--memory=768m', '--memory-swap=768m',
    '--cpus=1', '--pids-limit=48', '--ipc=private', '--shm-size=4m', '--ulimit', 'cpu=240:250',
    '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m,mode=1777', '--workdir', '/tmp',
    '--env', 'OMP_NUM_THREADS=1', '--env', 'OPENBLAS_NUM_THREADS=1', '--env', 'MKL_NUM_THREADS=1')
$deps = Join-Path $local 'deps'
New-Item -ItemType Directory -Path $deps -Force | Out-Null
if ($Phase -eq 'setup') {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'aqsol-linux-amd64.lock') -Destination (Join-Path $local 'wheels/lock.txt')
    & $docker @engine @limits --mount "type=bind,source=$local\wheels,target=/wheels,readonly" --mount "type=bind,source=$deps,target=/deps" --env TMPDIR=/deps $image python -B -m pip --isolated --disable-pip-version-check install --no-index --no-deps --no-cache-dir --require-hashes --find-links=/wheels --target=/deps -r /wheels/lock.txt
    exit $LASTEXITCODE
}
$files = @('lab.py','iris_pilot.py','aqsol_pilot.py','aqsol_model.py','aqsol-requirements.txt',
    'test_aqsol_pilot.py','test_aqsol_model.py','protocols/aqsol-solubility-v1.json')
if ($Phase -in @('preflight','run')) {
    $files += 'evidence/aqsol-v1-freeze.json'
    if ($Phase -eq 'run') { $files += 'evidence/aqsol-v1-admission.json' }
    $tracked = @($files | ForEach-Object { "lab/$_" })
    git ls-files --error-unmatch -- $tracked | Out-Null
    if ($LASTEXITCODE) { throw 'Freeze and sources must be committed' }
    git diff --quiet HEAD -- $tracked
    if ($LASTEXITCODE) { throw 'Freeze or tracked sources differ from HEAD' }
}
$bundle = Join-Path $local "bundle-$Phase"
foreach ($file in $files) {
    $target = Join-Path $bundle $file
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination $target
}
$mounts = @('--mount', "type=bind,source=$bundle,target=/pilot,readonly",
    '--mount', "type=bind,source=$deps,target=/deps,readonly", '--env', 'PYTHONPATH=/deps')
if ($Phase -eq 'test') {
    & $docker @engine @limits @mounts $image python -B -m unittest discover -s /pilot -p 'test_aqsol*.py' -v
    exit $LASTEXITCODE
}
$state = Join-Path $local 'state'
New-Item -ItemType Directory -Path $state -Force | Out-Null
$stateMode = if ($Phase -eq 'preflight') { ',readonly' } else { '' }
& $docker @engine @limits @mounts --mount "type=bind,source=$local\original.csv,target=/input.csv,readonly" --mount "type=bind,source=$state,target=/state$stateMode" $image python -B /pilot/aqsol_pilot.py $Phase /input.csv /state
exit $LASTEXITCODE
