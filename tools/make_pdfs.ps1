# Turn the two guides into PDFs.
#
#   powershell -File tools\make_pdfs.ps1
#
# Uses headless Chrome (or Edge) as the print engine, because the alternative
# is a second layout language for the same content. The HTML in docs/ is the
# source; the PDFs are output and can be regenerated at any time.
#
# Re-run this after tools/shots.js, which is what produces the screenshots the
# second guide is built around.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$docs = Join-Path $repo "docs"

$engine = @(
  "C:\Program Files\Google\Chrome\Application\chrome.exe",
  "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
  "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
  "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $engine) { throw "No Chrome or Edge found to print with." }
Write-Host "printing with $(Split-Path -Leaf $engine)"

$jobs = @(
  @{ src = "01-what-this-is.html";  out = "GoverningAI - What this is.pdf" },
  @{ src = "02-how-to-use-it.html"; out = "GoverningAI - How to use it.pdf" }
)

foreach ($job in $jobs) {
  $src = Join-Path $docs $job.src
  $out = Join-Path $docs $job.out
  if (-not (Test-Path $src)) { throw "Missing $src" }
  if (Test-Path $out) { Remove-Item -LiteralPath $out -Force -Confirm:$false }

  # A fresh profile each time: a warm one occasionally prints the previous
  # page, which is a very confusing bug to chase in a PDF.
  $profile = Join-Path $env:TEMP ("gaius-print-" + [guid]::NewGuid().ToString("N"))

  # Start-Process with -Wait rather than the call operator. Invoked directly,
  # Chrome handed the arguments to whatever instance was already running and
  # returned immediately with no exit code and no file — a silent no-op that
  # looks exactly like a permissions problem.
  #
  # --no-pdf-header-footer removes the URL and date Chrome otherwise stamps
  # into the margins of every page, which looks like a draft printout.
  # `$args` is a PowerShell automatic variable; assigning to it made Chrome
  # see two URLs and refuse with "Multiple targets are not supported".
  #
  # The paths are quoted by hand. Start-Process joins -ArgumentList with
  # spaces without quoting the elements, so "GoverningAI - What this is.pdf"
  # arrived as five separate arguments and Chrome refused with the same
  # "Multiple targets" error — it was counting the words in the filename.
  $flags = @(
    "--headless=new", "--disable-gpu", "--no-first-run",
    "--no-default-browser-check", "--run-all-compositor-stages-before-draw",
    "--virtual-time-budget=20000", "--no-pdf-header-footer",
    ('--user-data-dir="' + $profile + '"'),
    ('--print-to-pdf="' + $out + '"'),
    ("file:///" + $src.Replace("\", "/"))
  )
  $run = Start-Process -FilePath $engine -ArgumentList $flags -Wait -PassThru `
    -NoNewWindow
  if ($run.ExitCode -ne 0) { throw "$($job.src): chrome exited $($run.ExitCode)" }

  Remove-Item -LiteralPath $profile -Recurse -Force -ErrorAction SilentlyContinue

  if (Test-Path $out) {
    $kb = [math]::Round((Get-Item $out).Length / 1KB)
    Write-Host ("  {0}  ({1:N0} KB)" -f $job.out, $kb)
  } else {
    throw "Chrome produced no file for $($job.src)"
  }
}

Write-Host "`ndone - $docs"
