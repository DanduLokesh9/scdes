# Build a code-only deployment bundle.
#
# The server's own records are deliberately excluded. Overwriting
# corpus/audit/log.jsonl with a laptop copy would break the hash chain — the one
# property this application exists to guarantee — and the same reasoning applies
# to registrations, council decisions and the filled workbooks. Those are
# written on the server and belong to it.

$repo  = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $repo ".bundle1"
$zip   = Join-Path $env:TEMP "gai-latest.zip"

if (Test-Path -LiteralPath $stage) {
  Remove-Item -LiteralPath $stage -Recurse -Force -Confirm:$false
}
New-Item -ItemType Directory -Force -Path $stage | Out-Null

$excludeDirs = @(
  "__pycache__", ".pytest_cache", "node_modules", ".bundle1", ".git",
  (Join-Path $repo "corpus\audit"),
  (Join-Path $repo "corpus\registry"),
  (Join-Path $repo "corpus\index"),
  (Join-Path $repo "data"),
  (Join-Path $repo "council")
)

robocopy $repo $stage /E /NFL /NDL /NJH /NJS /NP /XD @excludeDirs /XF "*.pyc" "*.pem" | Out-Null

if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force -Confirm:$false }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory((Resolve-Path $stage), $zip)

"bundle : $zip"
"size   : {0:N1} MB" -f ((Get-Item $zip).Length / 1MB)
"files  : {0}" -f (Get-ChildItem $stage -Recurse -File).Count
""
"server records kept out of the bundle:"
foreach ($p in @("corpus\audit", "data", "council", "corpus\registry")) {
  $there = Test-Path -LiteralPath (Join-Path $stage $p)
  "  {0}  {1}" -f $(if ($there) { "STILL PRESENT" } else { "excluded     " }), $p
}
