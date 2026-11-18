# desinstaller.ps1 - Retire Runner de ce PC, en ne laissant aucune trace (lancé par desinstaller.bat,
# depuis une copie dans le dossier temporaire, pour pouvoir supprimer le dossier de Runner).
#
# Retiré : processus de Runner, connexions Google (révoquées chez Google), mots de passe et jetons
# du Gestionnaire d'identification, tâche planifiée de sortie de veille, raccourcis du Bureau et
# du Démarrage, fichiers temporaires, fichiers de Runner et son dossier. Python et les
# bibliothèques ne sont proposés à la désinstallation que si installer.bat les a lui-même installés
# (noté dans installation.json). Seuls les fichiers connus de Runner sont supprimés : un fichier
# qui n'est pas à lui est laissé en place, et le dossier n'est retiré que s'il est vide.

param([Parameter(Mandatory = $true)][string]$Dossier)
$ErrorActionPreference = "Continue"
$Dossier = [IO.Path]::GetFullPath($Dossier.TrimEnd('\', '.') + '\').TrimEnd('\')
$Avertissements = 0

function Titre($texte) { Write-Host ""; Write-Host $texte -ForegroundColor White }
function Ok($texte)    { Write-Host "  [OK] $texte" -ForegroundColor Green }
function Info($texte)  { Write-Host "       $texte" -ForegroundColor Gray }
function Alerte($texte){ Write-Host "  [!]  $texte" -ForegroundColor Yellow; $script:Avertissements++ }
function Fin {
    Write-Host ""
    Read-Host "Appuie sur Entrée pour fermer"
    exit
}
function Oui($question, $parDefaut) {
    $choix = if ($parDefaut) { "O/n" } else { "o/N" }
    $r = Read-Host "$question ($choix)"
    if (-not $r) { return $parDefaut }
    return $r.Trim().ToLower().StartsWith("o")
}

Write-Host "=================================" -ForegroundColor DarkYellow
Write-Host "   Runner - désinstallation" -ForegroundColor DarkYellow
Write-Host "=================================" -ForegroundColor DarkYellow
Info "Dossier : $Dossier"

# Sécurité : on ne touche qu'à un vrai dossier de Runner
if (-not ((Test-Path (Join-Path $Dossier "runner.py")) -and (Test-Path (Join-Path $Dossier "runner_reglages.py")))) {
    Write-Host ""
    Write-Host "Ce dossier ne contient pas Runner (runner.py et runner_reglages.py) : rien n'est fait." -ForegroundColor Red
    Fin
}

$Installation = $null
$FichierInstallation = Join-Path $Dossier "installation.json"
if (Test-Path $FichierInstallation) {
    try { $Installation = Get-Content -Raw $FichierInstallation | ConvertFrom-Json } catch { }
}
$Musiques = Join-Path $Dossier "musiques"

Write-Host ""
Write-Host "Runner va être retiré de ce PC :" -ForegroundColor White
Info "- ses réglages, son journal, ses fichiers et son dossier"
Info "- ses mots de passe et connexions mail (les connexions Google sont aussi révoquées chez Google)"
Info "- le lancement au démarrage, à la sortie de veille, et le raccourci du Bureau"
Info "- ses fichiers temporaires"
Write-Host ""
if (-not (Oui "Désinstaller Runner ?" $false)) {
    Write-Host "Rien n'a été modifié." -ForegroundColor Gray
    Fin
}
$GarderMusiques = $false
if ((Test-Path $Musiques) -and (Get-ChildItem $Musiques -Force -ErrorAction SilentlyContinue)) {
    $GarderMusiques = -not (Oui "Supprimer aussi tes musiques (dossier « musiques ») ?" $false)
}
$RetirerPaquets = $false
$Paquets = @()
if ($Installation -and $Installation.paquets) {
    $Paquets = @($Installation.paquets | Where-Object { $_ })
    if ($Paquets) {
        $RetirerPaquets = Oui "Désinstaller les bibliothèques Python ajoutées pour Runner ($($Paquets -join ', ')) ?" $true
    }
}
$RetirerPython = $false
if ($Installation -and $Installation.python_installe) {
    $RetirerPython = Oui "Python a été installé par Runner. Le désinstaller aussi ?" $true
}

# ---------------------------------------------------------------- 1. Processus
Titre "1. Arrêt de Runner"
$processus = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^pythonw?\.exe$|^pyw?\.exe$' -and $_.CommandLine -like "*$Dossier*" }
foreach ($p in $processus) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
Ok "Runner arrêté ($(@($processus).Count) processus)"
Start-Sleep -Milliseconds 800

# ---------------------------------------------------------------- 2. Connexions et mots de passe
Titre "2. Connexions et mots de passe"
$python = $null
if ($Installation -and $Installation.python -and (Test-Path $Installation.python)) { $python = $Installation.python }
elseif (Get-Command py -ErrorAction SilentlyContinue) { $python = "py" }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $python = "python" }
if ($python) {
    # Révocation chez Google et effacement des identifiants, par Runner lui-même
    Push-Location $Dossier
    & $python (Join-Path $Dossier "runner.py") --desinstaller 2>$null | ForEach-Object { Info $_ }
    Pop-Location
}
# Filet de sécurité (sans Python) : tout identifiant « Runner:… » restant est effacé
$restants = (cmdkey /list) | Select-String -Pattern '(LegacyGeneric:target=Runner:\S+)' -AllMatches |
    ForEach-Object { $_.Matches } | ForEach-Object { $_.Groups[1].Value }
foreach ($cible in $restants) { cmdkey /delete:$cible | Out-Null }
if ((cmdkey /list) -match 'target=Runner:') {
    Alerte "Des identifiants « Runner:… » restent dans le Gestionnaire d'identification : supprime-les à la main."
} else {
    Ok "Mots de passe et connexions effacés de Windows"
}
$gmail = $false
$config = Join-Path $Dossier "config.json"
if (Test-Path $config) {
    try {
        $cfg = Get-Content -Raw $config | ConvertFrom-Json
        $gmail = [bool]($cfg.infos.mails.comptes | Where-Object { $_.serveur -eq "imap.gmail.com" })
    } catch { }
}
if ($gmail) {
    Alerte "Gmail : supprime aussi le mot de passe d'application « Runner » sur la page Google qui va s'ouvrir."
    Start-Process "https://myaccount.google.com/apppasswords"
}

# ---------------------------------------------------------------- 3. Démarrage, veille, raccourcis
Titre "3. Lancement automatique et raccourcis"
schtasks /delete /f /tn "Runner\Reveil" 2>$null | Out-Null
try {                                            # le dossier « Runner » du Planificateur de tâches
    $planif = New-Object -ComObject Schedule.Service
    $planif.Connect()
    $racine = $planif.GetFolder("\")
    $dossierTaches = $racine.GetFolder("Runner")
    if ($dossierTaches.GetTasks(1).Count -eq 0) { $racine.DeleteFolder("Runner", 0) }
} catch { }
Ok "Tâche de sortie de veille retirée"
$shell = New-Object -ComObject WScript.Shell
foreach ($lien in @((Join-Path ([Environment]::GetFolderPath("Desktop")) "Runner.lnk"),
                    (Join-Path ([Environment]::GetFolderPath("Startup")) "Runner.lnk"))) {
    if (Test-Path -LiteralPath $lien) {
        # Seulement un raccourci qui lance bien Runner (pas un autre « Runner »)
        if ($shell.CreateShortcut($lien).Arguments -like "*$Dossier*") {
            Remove-Item -LiteralPath $lien -Force
        }
    }
}
Ok "Raccourcis du Bureau et du Démarrage retirés"

# ---------------------------------------------------------------- 4. Fichiers temporaires
Titre "4. Fichiers temporaires"
Get-ChildItem -Path $env:TEMP -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "runner_*" -or $_.Name -like "runner.wav*" } |
    Where-Object { $_.FullName -ne $PSCommandPath } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Ok "Fichiers temporaires de Runner supprimés"

# ---------------------------------------------------------------- 5. Bibliothèques et Python
if ($RetirerPaquets -and $python) {
    Titre "5. Bibliothèques Python"
    & $python -m pip uninstall -y --disable-pip-version-check @Paquets 2>$null | Out-Null
    Ok "Bibliothèques retirées : $($Paquets -join ', ')"
}
if ($RetirerPython) {
    Titre "6. Python"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        & winget uninstall --exact --id Python.Python.3.13 --silent --accept-source-agreements | Out-Null
        & winget uninstall --exact --id Python.Launcher --silent --accept-source-agreements 2>$null | Out-Null
        Ok "Python désinstallé"
    } else {
        Alerte "winget est indisponible : désinstalle Python depuis Paramètres > Applications."
    }
}

# ---------------------------------------------------------------- 7. Fichiers et dossier de Runner
Titre "Fichiers de Runner"
$fichiers = @("runner.py", "runner_reglages.py", "installer.bat", "installer.ps1", "desinstaller.bat",
              "desinstaller.ps1", "README.md", "DOCUMENTATION.md", "CHANGELOG.md", "PRIVACY.md", "TERMS.md",
              "LICENSE", "requirements.txt", ".gitignore", "runner.ico", "logo.png", "logo.svg",
              "config.json", "config.json.bak", "config.illisible.json", "google_client.json",
              "runner.log", "runner.ancien.log", "installation.json")
foreach ($f in $fichiers) { Remove-Item -LiteralPath (Join-Path $Dossier $f) -Force -ErrorAction SilentlyContinue }
Get-ChildItem -LiteralPath $Dossier -Filter "config.json.*.tmp" -Force -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
foreach ($d in @("cache_rythme", "__pycache__", "captures")) {
    Remove-Item -LiteralPath (Join-Path $Dossier $d) -Recurse -Force -ErrorAction SilentlyContinue
}
if (-not $GarderMusiques) { Remove-Item -LiteralPath $Musiques -Recurse -Force -ErrorAction SilentlyContinue }

$reste = @(Get-ChildItem -LiteralPath $Dossier -Force -ErrorAction SilentlyContinue)
if ($reste.Count -eq 0) {
    Set-Location $env:TEMP
    Remove-Item -LiteralPath $Dossier -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $Dossier) { Alerte "Le dossier vide n'a pas pu être supprimé : supprime-le à la main." }
    else { Ok "Dossier de Runner supprimé" }
} else {
    Ok "Fichiers de Runner supprimés"
    Info "Laissé en place dans $Dossier (pas créé par Runner, ou gardé) :"
    $reste | ForEach-Object { Info "  $($_.Name)" }
}

Write-Host ""
if ($Avertissements -eq 0) {
    Write-Host "Runner est désinstallé." -ForegroundColor Green
} else {
    Write-Host "Runner est désinstallé, avec les points en jaune ci-dessus à vérifier." -ForegroundColor Yellow
}
Write-Host ""
Read-Host "Appuie sur Entrée pour fermer"
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
