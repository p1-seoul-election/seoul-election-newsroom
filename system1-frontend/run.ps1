param([ValidateSet('dev','build','test','test:e2e')][string]$Task = 'dev')
Set-Location -LiteralPath $PSScriptRoot
New-Item -ItemType Directory -Force -Path '.runtime' | Out-Null
$env:TEMP = Join-Path $PSScriptRoot '.runtime'
$env:TMP = $env:TEMP
$env:npm_config_cache = Join-Path $PSScriptRoot '.runtime/npm-cache'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PSScriptRoot '.runtime/browsers'
npm run $Task
exit $LASTEXITCODE
