<#
.SYNOPSIS
  Prépare le dossier à pousser dans le Space Hugging Face (SDK Docker).

.DESCRIPTION
  Copie dans -Destination : Dockerfile et README.md (à la racine du Space), backend/ (code et dépendances,
  SANS .env, bases, PDF, MLflow, tests ni données de fine-tuning), frontend/ (sans node_modules ni dist) et
  deploy/hf-space/space_app.py. Le dossier obtenu ne contient aucun secret.

.EXAMPLE
  # depuis la racine du projet
  .\deploy\hf-space\prepare-space.ps1 -Destination ..\ai-study-assistant-space
#>
param(
    [Parameter(Mandatory = $true)][string]$Destination
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
New-Item -ItemType Directory -Force $Destination | Out-Null
$dest = (Resolve-Path $Destination).Path

# Fichiers propres au Space, à la racine
Copy-Item (Join-Path $PSScriptRoot "Dockerfile") (Join-Path $dest "Dockerfile") -Force
Copy-Item (Join-Path $PSScriptRoot "README.md") (Join-Path $dest "README.md") -Force
Copy-Item (Join-Path $PSScriptRoot "Dockerfile.dockerignore") (Join-Path $dest ".dockerignore") -Force
New-Item -ItemType Directory -Force (Join-Path $dest "deploy\hf-space") | Out-Null
Copy-Item (Join-Path $PSScriptRoot "space_app.py") (Join-Path $dest "deploy\hf-space\space_app.py") -Force

# robocopy : /E sous-dossiers, /XD dossiers exclus, /XF fichiers exclus ; codes de sortie < 8 = succès
function Copy-Tree($from, $to, $excludeDirs, $excludeFiles) {
    robocopy $from $to /E /NFL /NDL /NJH /NJS /NP /XD @excludeDirs /XF @excludeFiles | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Échec de la copie de $from (code robocopy $LASTEXITCODE)" }
}

Copy-Tree (Join-Path $root "backend") (Join-Path $dest "backend") `
    @(".venv", "__pycache__", ".pytest_cache", "storage", "mlruns", "tests", "results", "data", "notebooks") `
    @(".env", "*.db", "Dockerfile", ".dockerignore")
Copy-Item (Join-Path $root "backend\.env.example") (Join-Path $dest "backend\.env.example") -Force

Copy-Tree (Join-Path $root "frontend") (Join-Path $dest "frontend") `
    @("node_modules", "dist", ".angular", "coverage", ".vscode", ".idea") `
    @("Dockerfile", ".dockerignore", "nginx.conf")

# Vérification : aucun fichier de secrets ni de données
$forbidden = Get-ChildItem $dest -Recurse -Force -File |
    Where-Object { $_.Name -eq ".env" -or $_.Extension -eq ".db" -or $_.FullName -match "\\(storage|mlruns)\\" }
if ($forbidden) { throw "Fichiers interdits dans $dest : $($forbidden.FullName -join ', ')" }

Write-Host "Dossier du Space prêt : $dest"
Write-Host "Ensuite : hf upload Alinajjaa/ai-study-assistant `"$dest`" . --repo-type=space"
exit 0  # robocopy laisse un code de sortie 1 (« fichiers copiés ») qui n'est pas une erreur
