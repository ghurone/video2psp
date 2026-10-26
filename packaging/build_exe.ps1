<#
Builds the standalone Windows GUI with ffmpeg bundled, plus a release zip.

Usage (from the repo root, with video2psp and pyinstaller installed):
    powershell -File packaging\build_exe.ps1 -FfmpegDir <ffmpeg build folder> [-OneFile]

<ffmpeg build folder> is an extracted gyan.dev build: it must contain
bin\ffmpeg.exe, bin\ffprobe.exe and LICENSE.
#>
param(
    [Parameter(Mandatory = $true)] [string]$FfmpegDir,
    [switch]$OneFile
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ffmpeg = Resolve-Path $FfmpegDir
$name = "video2psp-gui"
# Everything is built in the temp folder and only the final zip is copied to
# dist\: in a synced folder (OneDrive) freshly written files can be locked,
# which breaks PyInstaller's cleanup and the zipping.
$work = Join-Path ([IO.Path]::GetTempPath()) "video2psp-build"
$dist = Join-Path $work "dist"

$mode = if ($OneFile) { "--onefile" } else { "--onedir" }
python -m PyInstaller --noconfirm --clean --windowed $mode `
    --name $name `
    --icon (Join-Path $PSScriptRoot "video2psp.ico") `
    --collect-data video2psp `
    --distpath $dist --workpath $work --specpath $work `
    --add-binary "$ffmpeg\bin\ffmpeg.exe;ffmpeg" `
    --add-binary "$ffmpeg\bin\ffprobe.exe;ffmpeg" `
    --copy-metadata video2psp `
    (Join-Path $PSScriptRoot "video2psp_gui.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# Release zip: the app plus the licenses the GPL requires us to ship with it.
$stage = Join-Path $work "zip\$name"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force $stage | Out-Null
if ($OneFile) {
    Copy-Item (Join-Path $dist "$name.exe") $stage
} else {
    Copy-Item -Recurse (Join-Path $dist "$name\*") $stage
}
Copy-Item (Join-Path $root "LICENSE") (Join-Path $stage "LICENSE.txt")
Copy-Item (Join-Path $ffmpeg "LICENSE") (Join-Path $stage "FFMPEG-LICENSE.txt")
@"
video2psp - https://github.com/ghurone/video2psp
Licensed under the GNU GPL v3 or later (LICENSE.txt). Source code: see the link above.

This package includes ffmpeg and ffprobe from https://www.gyan.dev/ffmpeg/builds/
(GPL build, see FFMPEG-LICENSE.txt). FFmpeg source code: https://ffmpeg.org/download.html
"@ | Out-File -Encoding utf8 (Join-Path $stage "README.txt")

$zip = Join-Path $dist "$name-windows.zip"
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path $stage -DestinationPath $zip
$outDir = Join-Path $root "dist"
New-Item -ItemType Directory -Force $outDir | Out-Null
Copy-Item -Force $zip $outDir
Write-Host "Built $(Join-Path $outDir "$name-windows.zip")"
