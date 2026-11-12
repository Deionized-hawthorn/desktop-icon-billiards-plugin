#Requires -Version 7.0
<#
.SYNOPSIS
    打包桌面图标台球（Desktop Icon Billiards）Windows x64 单文件 exe。

.DESCRIPTION
    版本号的唯一来源是 dib/__init__.py 的 __version__，本脚本在构建时读取它，
    再生成 build/version_info.txt 并传给 PyInstaller，因此 spec 和版本资源文件
    都不写死版本号。

    产物: dist/DesktopIconBilliards-<version>-win-x64.exe（不会删除 dist 里旧版本文件）。

    首次运行会用 uv 在仓库根目录创建 .venv 并安装 requirements-build.txt；
    Windows 10/11 x64 和 uv（https://docs.astral.sh/uv/）是前置条件，默认使用 uv 管理的 Python 3.12。

.PARAMETER SkipDeps
    跳过创建 .venv 和安装依赖，直接用已有的 .venv 打包（离线或 CI 复现构建时使用）。

.EXAMPLE
    pwsh -File build.ps1

.EXAMPLE
    pwsh -File build.ps1 -SkipDeps
#>
[CmdletBinding()]
param(
    [switch]$SkipDeps
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-Location -LiteralPath $PSScriptRoot

$repoRoot = $PSScriptRoot
$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
$venvDir = Join-Path $repoRoot '.venv'
$requirementsBuild = Join-Path $repoRoot 'requirements-build.txt'
$buildDir = Join-Path $repoRoot 'build'
$versionInfoFile = Join-Path $buildDir 'version_info.txt'
$distDir = Join-Path $repoRoot 'dist'
$workDir = Join-Path $buildDir 'pyinstaller'
$specFile = Join-Path $repoRoot 'DesktopIconBilliards.spec'

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Resolve-Uv {
    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    $fallback = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
    if (Test-Path -LiteralPath $fallback) {
        return $fallback
    }
    throw @'
未找到 uv，无法自动创建 .venv。
请先安装 uv: winget install --id=astral-sh.uv -e
或参考 https://docs.astral.sh/uv/ 安装后重新运行 build.ps1。
如果已经有可用的 .venv，可以改用: pwsh -File build.ps1 -SkipDeps
'@
}

if (-not $IsWindows) {
    throw '桌面图标台球只支持 Windows x64，请在 Windows 10/11 上运行 build.ps1。'
}

# ---------------------------------------------------------------------------
# 1. 虚拟环境
# ---------------------------------------------------------------------------
Write-Step '检查 Python 虚拟环境 (.venv)'
if (-not (Test-Path -LiteralPath $venvDir)) {
    if ($SkipDeps) {
        throw "未找到 .venv，且已指定 -SkipDeps。请去掉 -SkipDeps 让脚本自动创建，或手动执行: uv venv --managed-python --python 3.12 .venv"
    }
    $uv = Resolve-Uv
    Write-Step '创建虚拟环境 .venv'
    & $uv venv --managed-python --python 3.12 $venvDir
    if ($LASTEXITCODE -ne 0) {
        throw "创建 .venv 失败（uv 退出码 $LASTEXITCODE）。"
    }
}
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw '未找到 .venv\Scripts\python.exe。请重新创建 64 位 Python 虚拟环境后重试。'
}

# ---------------------------------------------------------------------------
# 2. 依赖
# ---------------------------------------------------------------------------
if ($SkipDeps) {
    Write-Step '已指定 -SkipDeps，跳过依赖安装，直接使用现有 .venv'
    & $venvPython -c 'import PyInstaller' 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw '当前 .venv 未安装 PyInstaller，无法使用 -SkipDeps。请先完整运行一次 build.ps1。'
    }
} else {
    $uv = Resolve-Uv
    Write-Step '安装构建依赖 (requirements-build.txt)'
    & $uv pip install --python $venvPython -r $requirementsBuild
    if ($LASTEXITCODE -ne 0) {
        throw "安装构建依赖失败（uv 退出码 $LASTEXITCODE）。"
    }
}

# ---------------------------------------------------------------------------
# 3. 版本号（唯一来源: dib/__init__.py 的 __version__）
# ---------------------------------------------------------------------------
Write-Step '读取版本号（来源: dib/__init__.py 的 __version__）'
$versionOutput = & $venvPython -c 'import dib; print(dib.__version__)'
if ($LASTEXITCODE -ne 0) {
    throw '读取版本号失败: 无法在当前 .venv 中导入 dib 包。请在仓库根目录运行，并确认 .venv 已安装依赖。'
}
$version = ([string]$versionOutput).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') {
    throw "版本号格式无效: '$version'。请把 dib/__init__.py 的 __version__ 改成 major.minor.patch（如 0.1.0）。"
}
Write-Host "    版本: $version"

# ---------------------------------------------------------------------------
# 4. 版本资源文件
# ---------------------------------------------------------------------------
Write-Step '生成 build/version_info.txt'
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
& $venvPython -X utf8 (Join-Path $repoRoot 'tools\gen_version_info.py') --version $version --output $versionInfoFile
if ($LASTEXITCODE -ne 0) {
    throw '生成版本信息失败（tools/gen_version_info.py 退出码非 0）。'
}
if (-not (Test-Path -LiteralPath $versionInfoFile)) {
    throw "生成版本信息失败: 未找到 $versionInfoFile"
}

# ---------------------------------------------------------------------------
# 5. PyInstaller
# ---------------------------------------------------------------------------
$env:DIB_VERSION = $version
$env:DIB_VERSION_INFO_FILE = $versionInfoFile
New-Item -ItemType Directory -Force -Path $distDir | Out-Null

Write-Step '运行 PyInstaller（单文件、窗口程序）'
Write-Host "    DIB_VERSION=$env:DIB_VERSION"
Write-Host "    DIB_VERSION_INFO_FILE=$env:DIB_VERSION_INFO_FILE"
& $venvPython -m PyInstaller --noconfirm --distpath $distDir --workpath $workDir $specFile
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 打包失败（退出码 $LASTEXITCODE）。"
}

# ---------------------------------------------------------------------------
# 6. 校验产物
# ---------------------------------------------------------------------------
$exePath = Join-Path $distDir "DesktopIconBilliards-$version-win-x64.exe"
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "打包完成但未找到预期产物: $exePath"
}

# A workspace may inherit a Low integrity label. An EXE carrying that label
# starts at Low integrity and cannot unpack into the user's normal temp folder.
# Normalize only the release file; leave workspace and system ACLs untouched.
Write-Step '设置发布 EXE 为普通用户完整性级别 (Medium)'
& icacls.exe $exePath /setintegritylevel M
if ($LASTEXITCODE -ne 0) {
    throw '无法设置发布 EXE 的 Medium 完整性标签。请在普通用户 PowerShell 中运行构建脚本。'
}

$exe = Get-Item -LiteralPath $exePath
$hash = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash
$sizeText = '{0:N1} MB' -f ($exe.Length / 1MB)

Write-Host ''
Write-Host '构建完成' -ForegroundColor Green
Write-Host "  文件:    $($exe.FullName)"
Write-Host "  版本:    $version"
Write-Host "  大小:    $sizeText ($($exe.Length) 字节)"
Write-Host "  SHA-256: $hash"
