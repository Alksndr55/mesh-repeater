[CmdletBinding()]
param(
    [string]$ToolchainBin,
    [string]$OutputDirectory = $PSScriptRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not $ToolchainBin) {
    $compiler = Get-Command 'avr-gcc.exe' -ErrorAction SilentlyContinue
    if ($compiler) {
        $ToolchainBin = Split-Path -Parent $compiler.Source
    } else {
        $arduinoTools = Join-Path $env:LOCALAPPDATA 'Arduino15\packages\arduino\tools\avr-gcc'
        $installed = Get-ChildItem -LiteralPath $arduinoTools -Directory -ErrorAction SilentlyContinue |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'bin\avr-gcc.exe') } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($installed) {
            $ToolchainBin = Join-Path $installed.FullName 'bin'
        }
    }
}

if (-not $ToolchainBin) {
    throw 'AVR toolchain not found. Use -ToolchainBin with the directory containing avr-gcc.exe.'
}

$ToolchainBin = (Resolve-Path -LiteralPath $ToolchainBin).Path
$toolPaths = @{}
foreach ($toolName in @('avr-gcc', 'avr-objcopy', 'avr-size')) {
    $toolPath = Join-Path $ToolchainBin ($toolName + '.exe')
    if (-not (Test-Path -LiteralPath $toolPath -PathType Leaf)) {
        throw "Missing tool: $toolPath"
    }
    $toolPaths[$toolName] = $toolPath
}

function Invoke-Avr {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "AVR command failed ($LASTEXITCODE): $Executable"
    }
}

$sourcePath = Join-Path $PSScriptRoot 'main.c'
if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    throw "Missing source: $sourcePath"
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$OutputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
$objectPath = Join-Path $OutputDirectory 'main.o'
$elfPath = Join-Path $OutputDirectory 'watchdog.elf'
$mapPath = Join-Path $OutputDirectory 'watchdog.map'
$hexPath = Join-Path $OutputDirectory 'watchdog.hex'

Invoke-Avr $toolPaths['avr-gcc'] @(
    '-std=gnu11', '-mmcu=attiny13a', '-DF_CPU=128000UL', '-Os', '-Wall', '-Wextra', '-Werror',
    '-ffunction-sections', '-fdata-sections', '-c', '-o', $objectPath, $sourcePath
)
Invoke-Avr $toolPaths['avr-gcc'] @(
    '-mmcu=attiny13a', '-Wl,--gc-sections', "-Wl,-Map=$mapPath", '-o', $elfPath, $objectPath
)
Invoke-Avr $toolPaths['avr-objcopy'] @('-O', 'ihex', '-R', '.eeprom', $elfPath, $hexPath)
Invoke-Avr $toolPaths['avr-size'] @('-C', '--mcu=attiny13a', $elfPath)
Write-Output "Built: $hexPath"
Write-Output 'Fuse bits are not included in Intel HEX and must be programmed separately.'
