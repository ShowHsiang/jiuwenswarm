# Bind an existing application venv to the SDK integration branch without re-resolving unrelated dependencies.
param(
    [string]$AgentCorePath = (Join-Path $PSScriptRoot '..\..\agent-core')
)
$ErrorActionPreference = 'Stop'
$appRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$sdkRoot = (Resolve-Path -LiteralPath $AgentCorePath).Path
$expectedBranch = 'react-runtime-bai'
$actualBranch = & git -C $sdkRoot branch --show-current
if ($LASTEXITCODE -ne 0 -or $actualBranch.Trim() -ne $expectedBranch) {
    throw "Expected agent-core branch $expectedBranch; found $actualBranch. Select the integration branch first."
}
$python = Join-Path $appRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'An existing jiuwenswarm .venv is required. This helper only replaces the SDK, not the application dependencies.'
}
$null = Get-Command uv -ErrorAction Stop
& uv pip install --python $python --no-deps --no-build-isolation --editable $sdkRoot
if ($LASTEXITCODE -ne 0) { throw 'Local SDK installation failed.' }
# Use the venv directly so uv does not replace the editable package from an older lockfile.
& $python -c 'import pathlib, sys; import openjiuwen.core.single_agent.runtime_monitor.monitor as m; source = pathlib.Path(m.__file__).resolve(); root = pathlib.Path(sys.argv[1]).resolve(); assert source.is_relative_to(root), source; print("SDK source:", source)' $sdkRoot
if ($LASTEXITCODE -ne 0) { throw 'Local SDK import verification failed.' }
Write-Host "SDK branch: $expectedBranch"
Write-Host 'Use .venv\Scripts\python.exe or uv run --no-sync for local integration.'
