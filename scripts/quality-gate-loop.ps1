param(
  [int]$IntervalMinutes = 30,
  [string]$Prompt = "Run a repository quality gate check and return a concise summary.",
  [string]$IssueSummaryFile = "agent_design_v6.md",
  [bool]$AutoInitGit = $true,
  [switch]$RunOnce,
  [switch]$NoPopup
)

$ErrorActionPreference = "Continue"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspace = Split-Path -Parent $scriptDir
Set-Location -Path $workspace
$logDir = Join-Path $workspace ".quality-gate-logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Normalize-Lines {
  param([object[]]$OutputObjects)

  return @(
    $OutputObjects |
      ForEach-Object { ("$_" -replace "`0", "").TrimEnd() }
  )
}

function Test-IsGitRepo {
  param([string]$Path)

  $null = & git -c safe.directory=* -C $Path rev-parse --is-inside-work-tree 2>$null
  return ($LASTEXITCODE -eq 0)
}

function Ensure-GitRepo {
  param(
    [string]$Path,
    [bool]$AllowAutoInit,
    [string]$LogFile
  )

  if (Test-IsGitRepo -Path $Path) {
    return $true
  }

  if (-not $AllowAutoInit) {
    return $false
  }

  $initOutput = & git -c safe.directory=* -C $Path init 2>&1
  $initLines = Normalize-Lines -OutputObjects @($initOutput)
  if ($initLines.Count -eq 0) {
    $initLines = @("[quality-gate] git init completed.")
  }

  $initLines | Out-File -FilePath $LogFile -Append -Encoding utf8
  return (Test-IsGitRepo -Path $Path)
}

function Get-IssueSummary {
  param(
    [string]$RootPath,
    [string]$PreferredFile
  )

  $candidates = @()

  if ($PreferredFile) {
    if ([System.IO.Path]::IsPathRooted($PreferredFile)) {
      $candidates += $PreferredFile
    } else {
      $candidates += (Join-Path $RootPath $PreferredFile)
    }
  }

  $candidates += @(
    (Join-Path $RootPath "CLAUDE.md"),
    (Join-Path $RootPath ".task"),
    (Join-Path $RootPath "TASK.md"),
    (Join-Path $RootPath "ISSUE.md")
  )

  $candidates = @($candidates | Where-Object { $_ } | Select-Object -Unique)

  foreach ($candidate in $candidates) {
    if (-not (Test-Path $candidate)) {
      continue
    }

    try {
      $firstLine = Get-Content -Path $candidate |
        Where-Object { $_ -and $_.Trim().Length -gt 0 } |
        Select-Object -First 1

      if (-not $firstLine) {
        continue
      }

      $clean = $firstLine.Trim() -replace '^[#>\-\*\d\.\)\s]+', ''
      if ($clean.Length -gt 180) {
        $clean = $clean.Substring(0, 180)
      }

      if ($clean.Length -gt 0) {
        return $clean
      }
    } catch {
      continue
    }
  }

  return "No explicit issue summary file detected."
}

function Build-RunPrompt {
  param(
    [string]$BasePrompt,
    [string]$IssueSummary
  )

  return @(
    "You are running a scheduled quality gate for the current repository.",
    "Do not call codex commands from inside this run.",
    "Analyze files in the current working directory only.",
    "Return exactly three lines with concrete values (no placeholders like <...>):",
    "Verdict: PASS|WARN|FAIL",
    "Problem: one concise concrete sentence.",
    "Suggestion: one actionable concrete sentence.",
    "Issue Summary: $IssueSummary",
    "Task: $BasePrompt"
  ) -join "`n"
}

function Get-ReportSummary {
  param([string[]]$Lines)

  $result = [ordered]@{
    Verdict    = "UNKNOWN"
    Problem    = "No issue summary detected."
    Suggestion = "No suggestion detected."
  }

  $wholeText = ($Lines -join "`n")

  $verdictLine = $Lines | Select-String -Pattern '^\s*Verdict:\s*(PASS|WARN|FAIL)\b' | Select-Object -Last 1
  if ($verdictLine) {
    $m = [regex]::Match($verdictLine.Line, '^\s*Verdict:\s*(PASS|WARN|FAIL)\b')
    if ($m.Success) {
      $result.Verdict = $m.Groups[1].Value
    }
  }

  $problemLine = $Lines | Select-String -Pattern '^\s*Problem:\s*(.+)$' | Select-Object -Last 1
  if ($problemLine) {
    $result.Problem = ([regex]::Match($problemLine.Line, '^\s*Problem:\s*(.+)$')).Groups[1].Value.Trim()
  }

  $suggestionLine = $Lines | Select-String -Pattern '^\s*Suggestion:\s*(.+)$' | Select-Object -Last 1
  if ($suggestionLine) {
    $result.Suggestion = ([regex]::Match($suggestionLine.Line, '^\s*Suggestion:\s*(.+)$')).Groups[1].Value.Trim()
  }

  if ($result.Problem -eq "No issue summary detected.") {
    $issueLine = $Lines | Select-String -Pattern 'deploy block|blocking issue|blocker|issue' | Select-Object -First 1
    if ($issueLine) {
      $result.Problem = $issueLine.Line.Trim()
    }
  }

  if ($result.Suggestion -eq "No suggestion detected.") {
    $fixLine = $Lines | Select-String -Pattern 'suggest|fix|proposal|next step|action' | Select-Object -First 1
    if ($fixLine) {
      $result.Suggestion = $fixLine.Line.Trim()
    }
  }

  if ($result.Verdict -eq "UNKNOWN" -and (
      $result.Problem -ne "No issue summary detected." -or
      $result.Suggestion -ne "No suggestion detected."
    )) {
    $result.Verdict = "WARN"
  }

  if ($result.Verdict -eq "UNKNOWN") {
    if ($wholeText -match '(?i)blocked by policy|rejected by policy') {
      $result.Verdict = "FAIL"
      $result.Problem = "Execution blocked by policy."
      $result.Suggestion = "Remove disallowed flags and avoid nested codex exec calls."
      return [pscustomobject]$result
    }

    if ($wholeText -match '(?i)not a git repository|outside a git repository|git repo check') {
      $result.Verdict = "FAIL"
      $result.Problem = "Workspace is not a Git repository."
      $result.Suggestion = "Run in a Git repo or enable AutoInitGit."
      return [pscustomobject]$result
    }
  }

  $placeholderPattern = '(?i)^(\s*<.+>\s*|one concise (concrete )?sentence\.?\s*|one actionable (concrete )?sentence\.?\s*|PASS\|WARN\|FAIL\s*)$'
  $isPlaceholderProblem = $result.Problem -match $placeholderPattern
  $isPlaceholderSuggestion = $result.Suggestion -match $placeholderPattern

  if ($isPlaceholderProblem -or $isPlaceholderSuggestion) {
    $result.Verdict = if ($result.Verdict -eq "FAIL") { "FAIL" } else { "WARN" }
    if ($isPlaceholderProblem) {
      $result.Problem = "Quality gate response used template text instead of a concrete issue summary."
    }
    if ($isPlaceholderSuggestion) {
      $result.Suggestion = "Tighten prompt/output parser or fallback to deterministic local checks."
    }
  }

  return [pscustomobject]$result
}

function Get-LocalFallbackSummary {
  param(
    [string]$RootPath,
    [string]$IssueSummary
  )

  $statusRaw = & git -c safe.directory=* -C $RootPath status --porcelain 2>&1
  if ($LASTEXITCODE -ne 0) {
    return [pscustomobject]@{
      Verdict    = "FAIL"
      Problem    = "Local Git status check failed."
      Suggestion = "Run quality gate in a valid Git repo and verify git access."
    }
  }

  $statusLines = @($statusRaw | ForEach-Object { ("$_").TrimEnd() } | Where-Object { $_ -and $_.Trim().Length -gt 0 })
  $conflictLine = $statusLines | Where-Object { $_ -match '^(UU|AA|DD|AU|UA|DU|UD)\s' } | Select-Object -First 1
  if ($conflictLine) {
    return [pscustomobject]@{
      Verdict    = "FAIL"
      Problem    = "Unmerged merge-conflict entries are present in Git status."
      Suggestion = "Resolve merge conflicts, then rerun quality gate."
    }
  }

  $srcCount = @(
    Get-ChildItem -Path $RootPath -Recurse -File -Include *.ps1,*.md,*.js,*.ts,*.tsx,*.json -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -notmatch '\\.git\\|\\node_modules\\|\\.quality-gate-logs\\' }
  ).Count

  if ($srcCount -eq 0) {
    return [pscustomobject]@{
      Verdict    = "WARN"
      Problem    = "No source files detected for meaningful quality evaluation."
      Suggestion = "Add project files or adjust quality-gate target path."
    }
  }

  if ($statusLines.Count -gt 0) {
    return [pscustomobject]@{
      Verdict    = "WARN"
      Problem    = "Working tree has $($statusLines.Count) pending Git change(s)."
      Suggestion = "Review changes for '$IssueSummary' and run lint/test before deploy."
    }
  }

  return [pscustomobject]@{
    Verdict    = "PASS"
    Problem    = "No blocking issue detected from local repository checks."
    Suggestion = "Keep periodic checks and monitor new changes."
  }
}

function Show-RunSummary {
  param(
    [string]$Verdict,
    [string]$Problem,
    [string]$Suggestion,
    [string]$LogFile,
    [bool]$ShowPopup = $true
  )

  $summary = @(
    "[quality-gate] summary",
    "Verdict: $Verdict",
    "Problem: $Problem",
    "Suggestion: $Suggestion"
  ) -join "`n"

  $summary | Out-File -FilePath $LogFile -Append -Encoding utf8
  Write-Host $summary

  if (-not $ShowPopup) {
    return
  }

  $popupText = $summary
  if ($popupText.Length -gt 900) {
    $popupText = $popupText.Substring(0, 900) + "..."
  }

  try {
    $wshell = New-Object -ComObject WScript.Shell
    $null = $wshell.Popup($popupText, 20, "Quality Gate Update", 64)
  } catch {
    $popupError = "[quality-gate] popup failed: $($_.Exception.Message)"
    $popupError | Out-File -FilePath $LogFile -Append -Encoding utf8
    Write-Host $popupError
  }
}

$claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
if ($claudeCmd) {
  $claudePath = $claudeCmd.Source
} else {
  $fallback = Join-Path $env:APPDATA "npm/claude.cmd"
  if (Test-Path $fallback) {
    $claudePath = $fallback
  } else {
    throw "claude command not found in PATH and fallback path."
  }
}

Write-Host "[quality-gate] loop started in $workspace"
Write-Host "[quality-gate] interval: $IntervalMinutes minutes"
Write-Host "[quality-gate] claude: $claudePath"
Write-Host "[quality-gate] auto init git: $AutoInitGit"
Write-Host "[quality-gate] run once: $RunOnce"
Write-Host "[quality-gate] stop with Ctrl+C"

while ($true) {
  $startedAt = Get-Date
  $stamp = $startedAt.ToString("yyyy-MM-dd HH:mm:ss")
  $dailyLog = Join-Path $logDir ("quality-gate-" + $startedAt.ToString("yyyyMMdd") + ".log")

  Write-Host ""
  Write-Host "[$stamp] running quality gate..."
  "[$stamp] running quality gate..." | Out-File -FilePath $dailyLog -Append -Encoding utf8

  if (-not (Ensure-GitRepo -Path $workspace -AllowAutoInit $AutoInitGit -LogFile $dailyLog)) {
    Show-RunSummary -Verdict "FAIL" -Problem "Workspace is not a Git repository." -Suggestion "Run git init in project root or point task to a Git repo." -LogFile $dailyLog -ShowPopup (-not $NoPopup)
    if ($RunOnce) {
      break
    }
    Start-Sleep -Seconds ($IntervalMinutes * 60)
    continue
  }

  $issueSummary = Get-IssueSummary -RootPath $workspace -PreferredFile $IssueSummaryFile
  $runPrompt = Build-RunPrompt -BasePrompt $Prompt -IssueSummary $issueSummary

  try {
    $runOutputObjects = & $claudePath -p $runPrompt 2>&1
    $runLines = Normalize-Lines -OutputObjects @($runOutputObjects)
    if ($runLines.Count -eq 0) {
      $runLines = @("[quality-gate] claude returned no output.")
    }

    $runLines | Out-File -FilePath $dailyLog -Append -Encoding utf8

    if ($LASTEXITCODE -ne 0) {
      "claude exit code: $LASTEXITCODE" | Out-File -FilePath $dailyLog -Append -Encoding utf8
    }

    $summary = Get-ReportSummary -Lines $runLines
    $needsLocalFallback = (
      $summary.Verdict -eq "UNKNOWN" -or
      $summary.Problem -eq "Quality gate response used template text instead of a concrete issue summary." -or
      $summary.Suggestion -eq "Tighten prompt/output parser or fallback to deterministic local checks."
    )
    if ($needsLocalFallback) {
      $fallback = Get-LocalFallbackSummary -RootPath $workspace -IssueSummary $issueSummary
      "local fallback summary applied" | Out-File -FilePath $dailyLog -Append -Encoding utf8
      $summary = $fallback
    }

    Show-RunSummary -Verdict $summary.Verdict -Problem $summary.Problem -Suggestion $summary.Suggestion -LogFile $dailyLog -ShowPopup (-not $NoPopup)
  } catch {
    $errLine = "[$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))] run failed: $($_.Exception.Message)"
    Write-Host $errLine
    $errLine | Out-File -FilePath $dailyLog -Append -Encoding utf8
    Show-RunSummary -Verdict "FAIL" -Problem "Quality gate run failed." -Suggestion "Check latest log tail and rerun manually." -LogFile $dailyLog -ShowPopup (-not $NoPopup)
  }

  if ($RunOnce) {
    break
  }

  $elapsedSec = [int]((Get-Date) - $startedAt).TotalSeconds
  $sleepSec = [Math]::Max(0, ($IntervalMinutes * 60) - $elapsedSec)
  Write-Host "[quality-gate] next run in $sleepSec seconds"
  Start-Sleep -Seconds $sleepSec
}
