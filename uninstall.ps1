# Uninstall vietsub skill from Cursor, Claude Code, or Antigravity (Windows).
# Usage:
#   ./uninstall.ps1 -Detect
#   ./uninstall.ps1 -DryRun
#   ./uninstall.ps1 -Yes

param(
    [string]$Tool = $(if ($env:VIETSUB_TOOL) { $env:VIETSUB_TOOL } else { "" }),
    [switch]$Detect,
    [switch]$DryRun,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$SkillName = "vietsub"
$ValidTools = @("cursor", "claude", "antigravity", "antigravity-project")

function Parse-ToolNames {
    param([string]$Input)
    $names = @()
    foreach ($part in ($Input -split ",")) {
        $name = $part.Trim()
        if (-not $name) { continue }
        if ($ValidTools -notcontains $name) {
            throw "Unknown tool: $name (use cursor | claude | antigravity | antigravity-project)"
        }
        if ($names -notcontains $name) { $names += $name }
    }
    return $names
}

function Get-DestPath {
    param([string]$Name)
    switch ($Name) {
        "cursor" { return Join-Path $env:USERPROFILE ".cursor\skills\$SkillName" }
        "claude" { return Join-Path $env:USERPROFILE ".claude\skills\$SkillName" }
        "antigravity" { return Join-Path $env:USERPROFILE ".gemini\config\skills\$SkillName" }
        "antigravity-project" { return Join-Path (Get-Location) ".agents\skills\$SkillName" }
    }
}

function Test-VietsubInstall {
    param([string]$Path)
    return (Test-Path $Path) -and (Test-Path (Join-Path $Path "SKILL.md"))
}

function Get-Targets {
    $targets = @()
    $tools = if ($Tool) { Parse-ToolNames $Tool } else { $ValidTools }

    foreach ($t in $tools) {
        $dest = if ($env:VIETSUB_INSTALL_DIR) { $env:VIETSUB_INSTALL_DIR } else { Get-DestPath $t }
        if (Test-VietsubInstall $dest) {
            $targets += [pscustomobject]@{ Tool = $t; Dest = $dest }
        }
    }
    return $targets
}

$targets = Get-Targets

if ($Detect -or $DryRun) {
    if ($targets.Count -eq 0) {
        Write-Host "No vietsub install found."
        exit 0
    }
    if ($Detect) {
        Write-Host "Installed vietsub skill:"
    } else {
        Write-Host "Would remove:"
    }
    foreach ($item in $targets) {
        Write-Host "  - [$($item.Tool)] $($item.Dest)"
    }
    exit 0
}

if ($targets.Count -eq 0) {
    Write-Host "No vietsub install found — nothing to remove."
    exit 0
}

if (-not $Yes) {
    Write-Host "Refusing to remove without -Yes."
    Write-Host ""
    Write-Host "Preview installed paths:"
    foreach ($item in $targets) {
        Write-Host "  - [$($item.Tool)] $($item.Dest)"
    }
    Write-Host ""
    Write-Host "Re-run with -Yes to uninstall, or use -DryRun to preview."
    exit 1
}

foreach ($item in $targets) {
    Write-Host "Removing [$($item.Tool)] $($item.Dest) ..."
    Remove-Item -Recurse -Force $item.Dest
}

Write-Host ""
Write-Host "Done. Removed $($targets.Count) vietsub install(s)."
Write-Host "Note: Python packages (pysubs2, chardet, …) are not removed."
Write-Host "Job folders (e.g. movie_batches/) are not removed — delete those manually if needed."
