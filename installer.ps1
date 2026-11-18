# installer.ps1 - Installe ou répare Runner sur ce PC (lancé par installer.bat).
#
# Vérifie Windows, Python (installé avec winget s'il manque), les bibliothèques, le micro,
# débloque les fichiers téléchargés et crée le raccourci « Runner » du Bureau.
# Relancé plus tard, il ne refait que ce qui manque : il sert aussi de réparation.
# Aucun droit administrateur n'est demandé. Runner reste dans le dossier de ce script.
# Ce que l'installeur ajoute lui-même (Python, bibliothèques) est noté dans installation.json :
# desinstaller.bat ne retirera que cela, jamais un Python ou une bibliothèque déjà présents.

# « Continue » : sous Windows PowerShell 5.1, en mode « Stop », le moindre avertissement écrit
# par Python ou pip arrêterait le script. Chaque étape vérifie elle-même son résultat.
$ErrorActionPreference = "Continue"
$Dossier = $PSScriptRoot
$Erreurs = 0

function Titre($texte) { Write-Host ""; Write-Host $texte -ForegroundColor White }
function Ok($texte)    { Write-Host "  [OK] $texte" -ForegroundColor Green }
function Info($texte)  { Write-Host "       $texte" -ForegroundColor Gray }
function Alerte($texte){ Write-Host "  [!]  $texte" -ForegroundColor Yellow }
function Echec($texte) { Write-Host "  [X]  $texte" -ForegroundColor Red; $script:Erreurs++ }

function Terminer {
    Write-Host ""
    if ($script:Erreurs -eq 0) {
        Write-Host "Installation terminée." -ForegroundColor Green
    } else {
        Write-Host "Installation incomplète : corrige les points en rouge puis relance installer.bat." -ForegroundColor Red
    }
    Write-Host ""
    Read-Host "Appuie sur Entrée pour fermer"
    exit $script:Erreurs
}

# Version de Python d'un exécutable, ou $null s'il ne marche pas (le faux « python » du
# Microsoft Store, par exemple, ne fait qu'afficher un message et renvoie une erreur).
function VersionPython($c) {
    try {
        $sortie = & $c.Exe @($c.Args) -c "import sys; print('%d.%d|%s' % (sys.version_info[0], sys.version_info[1], sys.executable))" 2>$null
        if ($LASTEXITCODE -eq 0 -and $sortie -match '^(\d+)\.(\d+)\|(.+)$') {
            return [pscustomobject]@{ Majeure = [int]$Matches[1]; Mineure = [int]$Matches[2]; Exe = $Matches[3].Trim() }
        }
    } catch { }
    return $null
}

# Cherche un Python 3.10 ou plus récent : lanceur « py », « python » du PATH, puis les
# dossiers d'installation habituels (utile juste après winget : le PATH de cette fenêtre
# n'est pas encore à jour).
function TrouverPython {
    $candidats = New-Object System.Collections.ArrayList
    if (Get-Command py -ErrorAction SilentlyContinue) { [void]$candidats.Add([pscustomobject]@{ Exe = "py"; Args = @("-3") }) }
    if (Get-Command python -ErrorAction SilentlyContinue) { [void]$candidats.Add([pscustomobject]@{ Exe = "python"; Args = @() }) }
    $dossiers = @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles\Python*", "${env:ProgramFiles(x86)}\Python*")
    foreach ($d in $dossiers) {
        Get-ChildItem -Path $d -Filter python.exe -Recurse -Depth 2 -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            ForEach-Object { [void]$candidats.Add([pscustomobject]@{ Exe = $_.FullName; Args = @() }) }
    }
    $meilleur = $null
    foreach ($c in $candidats) {
        $v = VersionPython $c
        if ($v -and $v.Majeure -eq 3 -and $v.Mineure -ge 10) {
            if (-not $meilleur -or $v.Mineure -gt $meilleur.Mineure) { $meilleur = $v }
        }
    }
    return $meilleur
}

$Version = ""
if ((Get-Content -Raw -ErrorAction SilentlyContinue (Join-Path $Dossier "runner.py")) -match 'VERSION = "([^"]+)"') {
    $Version = " " + $Matches[1]
}
# Ce que l'installeur a déjà installé lors d'un passage précédent (gardé d'une fois sur l'autre)
$FichierInstallation = Join-Path $Dossier "installation.json"
$Installation = @{ python_installe = $false; paquets = @() }
if (Test-Path $FichierInstallation) {
    try {
        $ancien = Get-Content -Raw $FichierInstallation | ConvertFrom-Json
        $Installation.python_installe = [bool]$ancien.python_installe
        $Installation.paquets = @($ancien.paquets | Where-Object { $_ })
    } catch { }
}

Write-Host "=================================" -ForegroundColor DarkYellow
Write-Host "   Runner$Version - installation" -ForegroundColor DarkYellow
Write-Host "=================================" -ForegroundColor DarkYellow
Info "Dossier : $Dossier"

# ---------------------------------------------------------------- 1. Fichiers et Windows
Titre "1. Fichiers et Windows"
if ($Dossier -match '\\AppData\\Local\\Temp\\') {
    Echec "Le zip n'a pas été décompressé : installer.bat a été lancé depuis l'intérieur du zip."
    Info "Fais un clic droit sur le zip > Extraire tout, puis lance installer.bat depuis le dossier extrait."
    Terminer
}
$manquants = @("runner.py", "runner_reglages.py") | Where-Object { -not (Test-Path (Join-Path $Dossier $_)) }
if ($manquants) {
    Echec "Fichiers manquants à côté de l'installeur : $($manquants -join ', ')"
    Terminer
}
Ok "Fichiers de Runner présents"
if (-not (Test-Path (Join-Path $Dossier "DOCUMENTATION.md"))) {
    Alerte "DOCUMENTATION.md manque : la page Aide de la fenêtre sera vide (la doc reste en ligne sur GitHub)."
}

$build = [Environment]::OSVersion.Version
if ($build.Major -lt 10) {
    Echec "Runner demande Windows 10 ou 11 (version trouvée : $build)."
    Terminer
}
Ok ("Windows " + $(if ($build.Build -ge 22000) { "11" } else { "10" }))

# Fichiers téléchargés : Windows les marque « venant d'Internet » et affiche un avertissement
# de sécurité à leur ouverture. On retire cette marque pour les fichiers de Runner.
try {
    Get-ChildItem -Path $Dossier -Recurse -File | Unblock-File -ErrorAction Stop
    Ok "Fichiers débloqués (plus d'avertissement de sécurité à l'ouverture)"
} catch {
    Alerte "Impossible de débloquer les fichiers : $($_.Exception.Message)"
}

# ---------------------------------------------------------------- 2. Python
Titre "2. Python"
$py = TrouverPython
if ($py) {
    Ok "Python $($py.Majeure).$($py.Mineure) trouvé"
} else {
    Info "Python 3.10 ou plus récent est introuvable : installation avec winget…"
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Echec "winget (l'installeur d'applis de Windows) n'est pas disponible sur ce PC."
        Info "Installe Python depuis la page qui va s'ouvrir, en cochant « Add python.exe to PATH »,"
        Info "puis relance installer.bat."
        Start-Process "https://www.python.org/downloads/"
        Terminer
    }
    & winget install --exact --id Python.Python.3.13 --scope user --silent `
        --accept-package-agreements --accept-source-agreements
    $py = TrouverPython
    if (-not $py) {
        Echec "Python ne s'est pas installé correctement."
        Info "Installe-le depuis https://www.python.org/downloads/ (coche « Add python.exe to PATH »),"
        Info "puis relance installer.bat."
        Terminer
    }
    Ok "Python $($py.Majeure).$($py.Mineure) installé"
    $Installation.python_installe = $true
}
$Python = $py.Exe
Info $Python

# Tkinter (fenêtre de réglages) fait partie de Python, mais peut avoir été décoché à l'installation
& $Python -c "import tkinter" 2>$null
if ($LASTEXITCODE -eq 0) {
    Ok "Fenêtres (tkinter) disponibles"
} else {
    Echec "tkinter manque : relance l'installeur de Python, choisis « Modify » et coche « tcl/tk and IDLE »."
}

# ---------------------------------------------------------------- 3. Bibliothèques
Titre "3. Bibliothèques"
$requirements = Join-Path $Dossier "requirements.txt"
# Bibliothèques absentes avant l'installation : notées pour la désinstallation
$bibliotheques = [ordered]@{ "sounddevice" = "sounddevice"; "numpy" = "numpy"; "soundfile" = "soundfile"; "edge_tts" = "edge-tts" }
foreach ($module in $bibliotheques.Keys) {
    & $Python -c "import $module" 2>$null
    if ($LASTEXITCODE -ne 0 -and $Installation.paquets -notcontains $bibliotheques[$module]) {
        $Installation.paquets += $bibliotheques[$module]
    }
}
Info "Installation ou mise à jour (connexion Internet nécessaire)…"
if (Test-Path $requirements) {
    & $Python -m pip install --upgrade --disable-pip-version-check --quiet -r $requirements
} else {
    & $Python -m pip install --upgrade --disable-pip-version-check --quiet sounddevice numpy soundfile edge-tts
}
# On vérifie que chacune se charge vraiment (une installation réussie ne suffit pas toujours)
foreach ($module in $bibliotheques.Keys) {
    & $Python -c "import $module" 2>$null
    if ($LASTEXITCODE -eq 0) { Ok $bibliotheques[$module] }
    else { Echec "$($bibliotheques[$module]) ne se charge pas (voir les messages de pip ci-dessus)" }
}
$Installation.version = $Version.Trim()
$Installation.python = $Python
$Installation | ConvertTo-Json | Set-Content -Encoding UTF8 $FichierInstallation
if ($Erreurs -gt 0) { Terminer }

# ---------------------------------------------------------------- 4. Micro
Titre "4. Micro"
$nbMicros = & $Python -c "import sounddevice as sd; print(sum(1 for d in sd.query_devices() if d['max_input_channels'] > 0))" 2>$null
if ($LASTEXITCODE -eq 0 -and [int]$nbMicros -gt 0) {
    Ok "$nbMicros entrée(s) audio détectée(s)"
} else {
    Alerte "Aucun micro détecté. Runner marchera quand même avec le raccourci clavier ;"
    Info   "branche un micro puis choisis-le dans la page Détection pour le double clap."
}

# ---------------------------------------------------------------- 5. Raccourci
Titre "5. Raccourci du Bureau"
# Même code que Runner lui-même (logo, lanceur Python qui survit aux mises à jour)
$code = "import sys; sys.path.insert(0, sys.argv[1]); import runner as cl; cl.reparer_raccourcis(bureau=True, forcer=True)"
& $Python -c $code $Dossier | Out-Null
# Vérification : chaque raccourci existe ET lance bien le script de ce dossier
$shell = New-Object -ComObject WScript.Shell
$attendus = @(
    @{ Nom = "du Bureau"; Lien = (Join-Path ([Environment]::GetFolderPath("Desktop")) "Runner.lnk"); Script = "runner_reglages.py"; Obligatoire = $true },
    @{ Nom = "du Démarrage"; Lien = (Join-Path ([Environment]::GetFolderPath("Startup")) "Runner.lnk"); Script = "runner.py"; Obligatoire = $false }
)
foreach ($r in $attendus) {
    if (-not (Test-Path -LiteralPath $r.Lien)) {
        if ($r.Obligatoire) { Echec "Le raccourci $($r.Nom) n'a pas pu être créé (voir runner.log dans le dossier de Runner)." }
        continue
    }
    $arguments = $shell.CreateShortcut($r.Lien).Arguments
    if ($arguments -like "*$(Join-Path $Dossier $r.Script)*") {
        Ok "Raccourci « Runner » $($r.Nom) à jour"
    } else {
        Echec "Le raccourci $($r.Nom) lance encore un autre fichier ($arguments)."
    }
}

# ---------------------------------------------------------------- Fin
if ($Erreurs -eq 0) {
    Titre "Ouverture de la fenêtre de réglages…"
    Info "Choisis ton micro, ta musique et tes applis, puis clique sur Enregistrer."
    $pythonw = Join-Path (Split-Path $Python) "pythonw.exe"
    if (-not (Test-Path $pythonw)) { $pythonw = $Python }
    Start-Process -FilePath $pythonw -ArgumentList "`"$(Join-Path $Dossier 'runner_reglages.py')`"" -WorkingDirectory $Dossier
}
Terminer
