<#
.SYNOPSIS
    Syncs one or more mailboxes from the old 4D cPanel IMAP server to the new
    Fasthosts IMAP server using imapsync (via Docker). Safe to re-run: imapsync
    only copies new/changed messages and never deletes anything by default.

.DESCRIPTION
    For each mailbox, you will be prompted interactively for the OLD (4D) and
    NEW (Fasthosts) passwords. Passwords are never written to this script,
    never echoed, and are written only to short-lived temp files (deleted
    immediately after each mailbox) so they never appear as process
    arguments or in shell history.

.PARAMETER Mailboxes
    List of mailbox addresses to sync. Defaults to the four primary addresses
    from docs/email-transfer-docs.md.

.PARAMETER DryRun
    If set, passes --dry to imapsync so nothing is actually transferred; use
    this first to preview folder mapping and message counts.

.EXAMPLE
    ./scripts/imapsync-sync.ps1 -DryRun
    ./scripts/imapsync-sync.ps1
    ./scripts/imapsync-sync.ps1 -Mailboxes 'manager@oxonxc.org.uk'
#>
param(
    [string[]]$Mailboxes = @(
        'committee@oxonxc.org.uk',
        'manager@oxonxc.org.uk',
        'touchbase@oxonxc.org.uk',
        'treasurer@oxonxc.org.uk'
    ),
    [switch]$DryRun
)

$OldHost = '51.68.226.210'
$OldPort = 993
$NewHost = 'mail.livemail.co.uk'
$NewPort = 993

$logDir = Join-Path $env:TEMP 'imapsync-logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Write-Host "imapsync logs will be written to: $logDir"

docker pull gilleslamiral/imapsync

foreach ($mailbox in $Mailboxes) {
    Write-Host "`n=== Syncing $mailbox ===" -ForegroundColor Cyan

    $oldSecure = Read-Host -AsSecureString "OLD (4D) password for $mailbox"
    $newSecure = Read-Host -AsSecureString "NEW (Fasthosts) password for $mailbox"

    $tempDir = Join-Path $env:TEMP ("imapsync-" + [guid]::NewGuid())
    New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
    $oldPassFile = Join-Path $tempDir 'old.txt'
    $newPassFile = Join-Path $tempDir 'new.txt'

    try {
        $bstrOld = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($oldSecure)
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstrOld) | Set-Content -NoNewline -Path $oldPassFile
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstrOld)

        $bstrNew = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($newSecure)
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstrNew) | Set-Content -NoNewline -Path $newPassFile
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstrNew)

        $logFile = Join-Path $logDir ("$mailbox".Replace('@', '_at_') + '.log')

        $dockerArgs = @(
            'run', '--rm', '-i',
            '-v', "${tempDir}:/passfiles:ro",
            'gilleslamiral/imapsync',
            'imapsync',
            '--host1', $OldHost, '--port1', $OldPort, '--user1', $mailbox, '--passfile1', '/passfiles/old.txt', '--ssl1',
            '--host2', $NewHost, '--port2', $NewPort, '--user2', $mailbox, '--passfile2', '/passfiles/new.txt', '--ssl2',
            '--automap', '--syncinternaldates', '--useheader', 'Message-Id'
        )
        if ($DryRun) { $dockerArgs += '--dry' }

        docker @dockerArgs 2>&1 | Tee-Object -FilePath $logFile
    }
    finally {
        Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
        $oldSecure = $null; $newSecure = $null
        [GC]::Collect()
    }
}

Write-Host "`nDone. Per-mailbox logs saved under $logDir" -ForegroundColor Green
