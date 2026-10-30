param([string]$Cxx)
$ErrorActionPreference = 'Stop'
if (-not $Cxx) {
    foreach ($name in @('clang++', 'g++', 'zig')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { $Cxx = $command.Source; break }
    }
}
if (-not $Cxx) { throw 'Specify -Cxx with the path to clang++, g++, or zig.' }
$taskTest = Join-Path ([IO.Path]::GetTempPath()) ('watchdog-host-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskTest | Out-Null
$exe = Join-Path $taskTest 'test_firmware.exe'
$compileArgs = @('-std=c++17', '-Wall', '-Wextra', '-Werror', '-I' + (Join-Path $PSScriptRoot 'include'),
                 (Join-Path $PSScriptRoot 'test_firmware.cpp'), '-o', $exe)
if ([IO.Path]::GetFileNameWithoutExtension($Cxx) -eq 'zig') { $compileArgs = @('c++') + $compileArgs }
& $Cxx @compileArgs
if ($LASTEXITCODE -ne 0) { throw "Host compilation failed: $LASTEXITCODE" }
& $exe
$result = $LASTEXITCODE
Write-Output "Host test executable: $exe"
if ($result -ne 0) { throw "Firmware regression tests failed: $result" }
