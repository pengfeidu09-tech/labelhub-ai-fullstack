# LabelHub 提交包清理脚本 (Windows PowerShell)
# 功能：从当前项目复制必要文件到临时目录，排除敏感/无关文件，打包为 zip

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path "$ProjectRoot\frontend")) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
$TempDir = "$env:TEMP\labelhub-submission-$(Get-Date -Format 'yyyyMMddHHmmss')"
$ZipName = "labelhub-ai-fullstack-submission.zip"
$ZipPath = Join-Path $ProjectRoot $ZipName

Write-Host "=== LabelHub 提交包清理 ===" -ForegroundColor Cyan
Write-Host "项目根目录: $ProjectRoot"
Write-Host "临时目录: $TempDir"

# Create temp directory
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

# Copy files with exclusions
$ExcludeDirs = @('.git', 'node_modules', 'dist', '.vite', '__pycache__', '.pytest_cache', 'migration_backup*', 'backup', 'exports', '.qoder')
$ExcludeFiles = @('.env', '.env.local', '*.pyc', '*.log', '*.db-journal', '*.db.bak', 'labelhub_backup_*.db', '*.zip')

# Use robocopy for efficient copying
$robocopyArgs = @($ProjectRoot, $TempDir, '/E', '/XD')
$robocopyArgs += $ExcludeDirs
$robocopyArgs += '/XF'
$robocopyArgs += $ExcludeFiles
$robocopyArgs += '/NFL', '/NDL', '/NJH', '/NJS'

Write-Host "复制文件中..." -ForegroundColor Yellow
& robocopy @robocopyArgs

# Remove any .env files that could have slipped through
Get-ChildItem -Path $TempDir -Filter ".env" -Recurse | Remove-Item -Force
Get-ChildItem -Path $TempDir -Filter ".env.local" -Recurse | Remove-Item -Force

# Create zip
Write-Host "打包中..." -ForegroundColor Yellow
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path "$TempDir\*" -DestinationPath $ZipPath -CompressionLevel Optimal

# Clean up temp
Remove-Item -Path $TempDir -Recurse -Force

# Print result
$zipSize = (Get-Item $ZipPath).Length / 1MB
Write-Host "`n=== 打包完成 ===" -ForegroundColor Green
Write-Host "文件: $ZipPath"
Write-Host ("大小: {0:N1} MB" -f $zipSize)

# Validation checks
Write-Host "`n=== 安全检查 ===" -ForegroundColor Cyan
Add-Type -Assembly System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
$issues = @()
foreach ($entry in $zip.Entries) {
    if ($entry.FullName -match '\.env$' -or $entry.FullName -match '\.env\.local$') { $issues += "发现 .env: $($entry.FullName)" }
    if ($entry.FullName -match 'node_modules') { $issues += "发现 node_modules: $($entry.FullName)" }
    if ($entry.FullName -match '\.git/') { $issues += "发现 .git: $($entry.FullName)" }
    if ($entry.FullName -match 'dist/') { $issues += "发现 dist: $($entry.FullName)" }
}
$zip.Dispose()

if ($issues.Count -gt 0) {
    Write-Host "发现问题：" -ForegroundColor Red
    $issues | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
} else {
    Write-Host "所有安全检查通过！" -ForegroundColor Green
}
