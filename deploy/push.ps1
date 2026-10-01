# Copy the app to the server and run the bootstrap. Windows side.
#
#   powershell -File deploy\push.ps1
#
# Safe to re-run: it replaces the code and restarts the service, leaving the
# audit log, registrations and filled workbooks alone — those live in
# corpus/audit, data/ and corpus/registry on the server and are never
# overwritten, because losing them would break the hash chain.

param(
  [string]$Key    = "C:\Users\dandu\Downloads\govern.pem",
  [string]$Host_  = "107.21.44.130",
  [string]$User   = "ubuntu",
  [switch]$SetupOnly,
  [switch]$CodeOnly
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$zip  = Join-Path $env:TEMP "governingai-deploy.zip"
$ssh  = "ssh -i `"$Key`" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 $User@$Host_"

function Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }

# ------------------------------------------------------------ pre-flight

Step "Checking the key and the connection"
if (-not (Test-Path $Key)) { throw "Key not found: $Key" }

$probe = New-Object System.Net.Sockets.TcpClient
$open = $false
try { $open = $probe.ConnectAsync($Host_, 22).Wait(8000) -and $probe.Connected } catch {} finally { $probe.Close() }
if (-not $open) {
  Write-Host "  Port 22 on $Host_ is not answering." -ForegroundColor Yellow
  Write-Host "  This is almost always the EC2 security group. In the AWS console:"
  Write-Host "    EC2 > Instances > i-0a8d06f88ec69f8be > Security tab > the security group"
  Write-Host "    Edit inbound rules, then add:  SSH 22, HTTP 80, HTTPS 443"
  throw "Cannot reach the server on port 22."
}
Write-Host "  port 22 is open"

# ------------------------------------------------------------- the code

if (-not $SetupOnly) {
  Step "Packaging the app"
  # Code only. The server's own records are deliberately NOT in the bundle:
  # overwriting corpus/audit/log.jsonl with a laptop copy would break the hash
  # chain, which is the one property this application exists to guarantee. Same
  # for registrations, council decisions and the filled workbooks — those are
  # written on the server and belong to it.
  #
  # corpus/config is a split case, and the /XF list below is the split. The
  # tuned reference regime ships — risk_model, budget, categories, procurement,
  # vision, capabilities, brand — because that is IIA's document set and a
  # deploy is how it gets updated. The files an *agency* creates by using the
  # platform do not:
  #
  #   framework_adoption.json   whether a version was adopted
  #   framework_versions.json   every answer, and every saved version
  #   decider.json              who the framework named as its decision-maker
  #   mode.json                 configuration mode vs operating mode
  #
  # A laptop had an adoption record the server did not. Pushing it would have
  # made staging announce that its framework was adopted, dropping the DRAFT
  # stamp off exported documents on the strength of a file that arrived by scp.
  # Same class of mistake as overwriting the audit log, and quieter.
  #
  # .env is excluded because it holds the API key for the writing tool, and a
  # secret has no business in a zip that lands in /tmp on a shared box. The
  # server keeps its own copy at /etc/governingai.env, root-owned and 0600,
  # which is where the service reads it from — so a deploy cannot overwrite
  # the server's key with a laptop's, or ship a laptop's key anywhere.
  #
  # app/web/assets/speech is excluded for a different reason: it is 60 MB of
  # dictation runtime and model that changes roughly never. Shipping it in every
  # deploy would add a minute to each push for bytes that are already there.
  # Placed on the server once:
  #
  #   python -m tools.fetch_speech          (locally, or on the box)
  #   scp -r app/web/assets/speech ubuntu@host:/opt/governingai/app/web/assets/
  # Cleared rather than reused. robocopy without /PURGE only adds, so a file
  # deleted from the repo stayed in the staging directory and shipped again on
  # every later push — `app/workflow.py` was still going up months after it was
  # retired, along with five old server logs and a couple of probe documents.
  # Nothing here is worth keeping between pushes; the bundle is derived.
  $stage = Join-Path $repo ".bundle1"
  if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force -Confirm:$false }
  New-Item -ItemType Directory -Force -Path $stage | Out-Null
  robocopy $repo $stage /E /NFL /NDL /NJH /NJS /NP `
    /XD "__pycache__" ".pytest_cache" "node_modules" ".bundle1" ".git" `
        "$repo\corpus\audit" "$repo\corpus\registry" "$repo\corpus\index" `
        "$repo\data" "$repo\council" `
        "$repo\app\web\assets\speech" `
        "$repo\docs" `
    /XF "*.pyc" "*.pem" ".env" `
        "framework_adoption.json" "framework_versions.json" "decider.json" `
        "mode.json" | Out-Null
  if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force -Confirm:$false }
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  [System.IO.Compression.ZipFile]::CreateFromDirectory((Resolve-Path $stage), $zip)
  Write-Host ("  {0:N1} MB packaged" -f ((Get-Item $zip).Length / 1MB))

  Step "Uploading"
  & scp -i "$Key" -o StrictHostKeyChecking=accept-new $zip "${User}@${Host_}:/tmp/app.zip"
  if ($LASTEXITCODE -ne 0) { throw "scp failed" }

  Step "Unpacking into /opt/governingai"
  # -o overwrites code; the data directories are not in the archive, so a
  # re-deploy cannot clobber the audit log.
  $unpack = "sudo mkdir -p /opt/governingai && sudo chown -R ubuntu:ubuntu /opt/governingai && sudo apt-get install -y -qq unzip >/dev/null 2>&1; unzip -oq /tmp/app.zip -d /opt/governingai && chmod +x /opt/governingai/deploy/*.sh && ls /opt/governingai | head"
  Invoke-Expression "$ssh `"$unpack`""
}

# ---------------------------------------------------------------- bootstrap

if (-not $CodeOnly) {
  Step "Running the server bootstrap (this takes a few minutes the first time)"
  Invoke-Expression "$ssh `"cd /opt/governingai && bash deploy/setup_server.sh`""
} else {
  Step "Restarting the service"
  Invoke-Expression "$ssh `"sudo systemctl restart governingai && sleep 2 && sudo systemctl is-active governingai`""
}

Step "Done"
Write-Host "  http://app.staging.governingai.us"
Write-Host "  Then, for HTTPS:  ssh in and run  bash deploy/enable_tls.sh you@your.email"
