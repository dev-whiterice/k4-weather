# Installs the dashboard on the Kindle from Windows.
#
#     .\kindle\install.ps1                       # over SSH, root@192.168.15.244
#     .\kindle\install.ps1 root@192.168.1.50     # over SSH, another address
#     .\kindle\install.ps1 -Drive E:             # onto the Kindle as a USB disk
#
# This is a wrapper and nothing more: the installation itself lives in
# install.sh, which runs under the bash that comes with Git for Windows. There
# is no second implementation to keep in step, on purpose — the install has to
# patch a shell script line by line and copy a tree, and a PowerShell rewrite of
# that would be a second thing to debug on a device with no terminal.
#
# So all this does is find that bash and hand over to it, with an error worth
# reading if it is not there.

[CmdletBinding()]
param(
    # The Kindle mounted as a USB drive: E:, E:\, or a path. When given, nothing
    # touches the network at all — see "Without SSH" in kindle/README.md.
    [string]$Drive = "",

    # user@host of the Kindle over USBNetwork or Wi-Fi. Ignored with -Drive.
    [Parameter(Position = 0)]
    [string]$Kindle = ""
)

$ErrorActionPreference = "Stop"

# git.exe is on PATH far more often than bash.exe is, and bash sits at a known
# place relative to it: Git\cmd\git.exe -> Git\bin\bash.exe.
function Find-GitBash {
    $candidates = @()

    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($git) {
        $root = Split-Path (Split-Path $git.Source -Parent) -Parent
        $candidates += (Join-Path $root "bin\bash.exe")
    }

    $bash = Get-Command bash.exe -ErrorAction SilentlyContinue
    if ($bash) {
        # Not every bash.exe on PATH is Git Bash — the WSL launcher is called
        # bash.exe too, and it cannot see this checkout the way install.sh
        # expects. Only accept one that did not come from System32.
        if ($bash.Source -notlike "*\System32\*") { $candidates += $bash.Source }
    }

    $candidates += "$env:ProgramFiles\Git\bin\bash.exe"
    $candidates += "${env:ProgramFiles(x86)}\Git\bin\bash.exe"
    $candidates += "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    return $null
}

# D:\Developer\k4-weather\... -> /d/Developer/k4-weather/...
function ConvertTo-PosixPath([string]$WindowsPath) {
    $posix = $WindowsPath -replace '\\', '/'
    if ($posix -match '^([A-Za-z]):(.*)$') {
        $posix = "/" + $Matches[1].ToLower() + $Matches[2]
    }
    return $posix
}

$bashExe = Find-GitBash
if (-not $bashExe) {
    Write-Error @"
Git Bash was not found.

install.sh is a shell script and needs the bash that ships with Git for
Windows. Install it from https://git-scm.com/download/win and run this again,
or run the script directly from a Git Bash window.
"@
    exit 1
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installSh = Join-Path $scriptDir "install.sh"
if (-not (Test-Path $installSh)) {
    Write-Error "install.sh is not next to install.ps1 (looked in $scriptDir)"
    exit 1
}

# Checked here rather than left to install.sh, because the message can be much
# more specific from this side: PowerShell knows which drives exist and what
# they are called.
if ($Drive) {
    $probe = $Drive
    if ($probe -match '^[A-Za-z]:?$') { $probe = $probe.Substring(0, 1) + ":\" }
    if (-not (Test-Path $probe)) {
        $removable = Get-Volume |
            Where-Object { $_.DriveType -eq 'Removable' -and $_.DriveLetter } |
            ForEach-Object { "  $($_.DriveLetter): $($_.FileSystemLabel)" }
        $seen = if ($removable) { ($removable -join "`n") } else { "  (none)" }
        Write-Error @"
$Drive is not there.

Removable drives currently mounted:
$seen

If the Kindle is not among them it is not in USB drive mode: in usbnet mode it
is a network device and not a disk. Type ;un into the Kindle's search box to
toggle that off, and it comes back as a drive.
"@
        exit 1
    }
}

$posixPath = ConvertTo-PosixPath $installSh

# Built as an argument list and then quoted once, so a path with a space in it
# survives. Single quotes because bash -lc takes one string: nothing here can
# contain a single quote (a drive letter, a user@host, an install path that
# Test-Path already accepted), so no escaping beyond this is needed.
$argv = @($posixPath)
if ($Drive) {
    $argv += "--drive"
    $argv += $Drive
} elseif ($Kindle) {
    $argv += $Kindle
}
$commandLine = ($argv | ForEach-Object { "'" + $_ + "'" }) -join " "

Write-Host "==> $bashExe -lc $commandLine" -ForegroundColor Cyan

& $bashExe -lc $commandLine

exit $LASTEXITCODE
