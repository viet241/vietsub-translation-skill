# Install vietsub skill for Cursor, Claude Code, or Antigravity (Windows).
# Usage:
#   irm .../install.ps1 | iex
#   $env:VIETSUB_TOOL="claude"; irm .../install.ps1 | iex
#   irm ... -OutFile install.ps1; .\install.ps1 -Tool cursor,claude
#   .\install.ps1 -Interactive

param(
    [string]$Tool = $(if ($env:VIETSUB_TOOL) { $env:VIETSUB_TOOL } else { "" }),
    [switch]$Interactive,
    [switch]$Detect,
    [switch]$Reinstall
)

$ErrorActionPreference = "Stop"

$RepoUrl = if ($env:VIETSUB_REPO_URL) { $env:VIETSUB_REPO_URL } else { "https://github.com/viet241/vietsub-translation-skill.git" }
$RepoBranch = if ($env:VIETSUB_REPO_BRANCH) { $env:VIETSUB_REPO_BRANCH } else { "main" }
$SkillName = "vietsub"
$ValidTools = @("cursor", "claude", "antigravity", "antigravity-project")

function Get-DestPath {
    param([string]$Name)
    switch ($Name) {
        "cursor" { return Join-Path $env:USERPROFILE ".cursor\skills\$SkillName" }
        "claude" { return Join-Path $env:USERPROFILE ".claude\skills\$SkillName" }
        "antigravity" { return Join-Path $env:USERPROFILE ".gemini\config\skills\$SkillName" }
        "antigravity-project" { return Join-Path (Get-Location) ".agents\skills\$SkillName" }
        default { throw "Unknown tool: $Name" }
    }
}

function Get-InvokeHint {
    param([string]$Name)
    if ($Name -in @("cursor", "claude")) { return "/vietsub" }
    return "follow SKILL.md or invoke skill"
}

function Test-HasCursor {
    return (Test-Path (Join-Path $env:USERPROFILE ".cursor")) `
        -or (Get-Command cursor -ErrorAction SilentlyContinue)
}

function Test-HasClaude {
    return (Test-Path (Join-Path $env:USERPROFILE ".claude")) `
        -or (Get-Command claude -ErrorAction SilentlyContinue)
}

function Test-HasAntigravity {
    return (Test-Path (Join-Path $env:USERPROFILE ".gemini\config\skills")) `
        -or (Test-Path (Join-Path $env:USERPROFILE ".gemini\config")) `
        -or (Test-Path (Join-Path $env:USERPROFILE ".agents\skills"))
}

function Get-DetectedTools {
    $found = @()
    if (Test-HasCursor) { $found += "cursor" }
    if (Test-HasClaude) { $found += "claude" }
    if (Test-HasAntigravity) { $found += "antigravity" }
    return $found
}

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

function Choose-ToolsInteractive {
    param([string[]]$Detected)

    if ($Detected.Count -eq 0) {
        Write-Host "No agent tools detected. Enter tool names (comma-separated):"
        Write-Host "  cursor | claude | antigravity | antigravity-project"
        $choice = Read-Host ">"
        return Parse-ToolNames $choice
    }

    Write-Host "Choose tools to install:"
    for ($i = 0; $i -lt $Detected.Count; $i++) {
        $path = Get-DestPath $Detected[$i]
        Write-Host ("  {0}) {1}  -> {2}" -f ($i + 1), $Detected[$i], $path)
    }
    Write-Host "  a) all"
    $choice = Read-Host "Choice [a / number / cursor,claude]"

    $choice = $choice.Trim()
    if (-not $choice -or $choice -eq "a" -or $choice -eq "all") {
        return $Detected
    }

    if ($choice -match '^[\d,]+$') {
        $picked = @()
        foreach ($num in ($choice -split ",")) {
            $idx = [int]$num
            if ($idx -lt 1 -or $idx -gt $Detected.Count) {
                throw "Invalid choice: $num"
            }
            $picked += $Detected[$idx - 1]
        }
        return $picked
    }

    return Parse-ToolNames $choice
}

function Get-PythonCmd {
    if (Get-Command py -ErrorAction SilentlyContinue) { return "py" }
    if (Get-Command python -ErrorAction SilentlyContinue) { return "python" }
    throw "Python not found. Install Python 3.10+ and retry."
}

function Install-ForTool {
    param([string]$Name)

    $dest = if ($env:VIETSUB_INSTALL_DIR -and $Name -ne "antigravity-project") {
        $env:VIETSUB_INSTALL_DIR
    } else {
        Get-DestPath $Name
    }
    $invoke = Get-InvokeHint $Name
    $parent = Split-Path $dest -Parent

    Write-Host ""
    Write-Host "==> Installing for $Name"

    if (Test-Path $dest) {
        if ($Reinstall) {
            Remove-Item -Recurse -Force $dest
        }
        elseif (Test-Path (Join-Path $dest ".git")) {
            Write-Host "Updating $dest ..."
            git -C $dest fetch origin $RepoBranch
            git -C $dest checkout $RepoBranch
            git -C $dest pull --ff-only origin $RepoBranch
            return [pscustomobject]@{ Tool = $Name; Dest = $dest; Invoke = $invoke }
        }
        else {
            throw "$dest exists and is not a git repo. Use -Reinstall."
        }
    }

    if (-not (Test-Path $dest)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
        Write-Host "Cloning $RepoUrl -> $dest"
        git clone --branch $RepoBranch --depth 1 $RepoUrl $dest
    }

    return [pscustomobject]@{ Tool = $Name; Dest = $dest; Invoke = $invoke }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git not found. Install Git and retry."
}

$Python = Get-PythonCmd
$detected = Get-DetectedTools

if ($Detect) {
    if ($detected.Count -eq 0) {
        Write-Host "No agent tools detected."
        Write-Host "Hints: %USERPROFILE%\.cursor, %USERPROFILE%\.claude, %USERPROFILE%\.gemini\config"
        Write-Host "You can still install with: -Tool cursor"
        exit 1
    }
    Write-Host "Detected agent tools:"
    foreach ($t in $detected) {
        Write-Host "  - $t  -> $(Get-DestPath $t)"
    }
    exit 0
}

$tools = @()
if ($Tool) {
    $tools = Parse-ToolNames $Tool
}
elseif ($Interactive -or (($MyInvocation.MyCommand.Path) -and $detected.Count -gt 1)) {
    $tools = Choose-ToolsInteractive $detected
}
elseif ($detected.Count -gt 0) {
    $tools = $detected
}

if ($tools.Count -eq 0) {
    Write-Host @"
No install target selected.

Examples:
  irm .../install.ps1 | iex
  `$env:VIETSUB_TOOL='claude'; irm .../install.ps1 | iex
  .\install.ps1 -Tool cursor,claude
  .\install.ps1 -Interactive

Run .\install.ps1 -Detect to list detected tools.
"@
    exit 1
}

if (-not $Tool -and -not $Interactive) {
    Write-Host "Installing for: $($tools -join ', ')"
}

$installed = @()
foreach ($t in $tools) {
    $installed += Install-ForTool $t
}

if ($installed.Count -gt 0) {
    Write-Host ""
    Write-Host "Installing Python dependencies ..."
    & $Python -m pip install -r (Join-Path $installed[0].Dest "requirements.txt")
}

Write-Host ""
Write-Host "Done. vietsub installed for $($installed.Count) target(s):"
foreach ($item in $installed) {
    Write-Host ""
    Write-Host "  [$($item.Tool)] $($item.Dest)"
    Write-Host "    invoke: $($item.Invoke)"
}
Write-Host ""
Write-Host "Requires Python 3.10+ (dependencies installed via pip)."
