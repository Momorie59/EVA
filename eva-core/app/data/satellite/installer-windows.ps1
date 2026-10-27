# Installe un satellite vocal d'EVA sur Windows et le lance à l'ouverture de session.
#   powershell -ExecutionPolicy Bypass -File installer-windows.ps1 -Eva https://192.168.1.10:8443 -Jeton evasat_XXXXXXXX
#   options du PC : -Fenetre -Tableau -Ecran -Gestes  (ex. tout : -Fenetre -Tableau -Ecran -Gestes)
param([Parameter(Mandatory = $true)][string]$Eva, [Parameter(Mandatory = $true)][string]$Jeton, [string]$Eveil = "whisper",
      [switch]$Fenetre, [switch]$Tableau, [switch]$Ecran, [switch]$Gestes,
      [string]$Profil = $env:USERPROFILE, [string]$Compte = "$env:USERDOMAIN\$env:USERNAME")
$ErrorActionPreference = "Stop"
$Eva = $Eva.TrimEnd("/")
if (-not $Profil -or -not (Test-Path $Profil)) { $Profil = $env:USERPROFILE }
$Dossier = Join-Path $Profil "eva-satellite"
$Admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($Admin) { Write-Host "== Droits administrateur : oui (compte du satellite : $Compte)" -ForegroundColor Green }
else { Write-Host "== Sans droits administrateur : le satellite ne pourra pas agir sur les fenêtres ouvertes en administrateur." -ForegroundColor Yellow }
# Dossiers de la personne (et non du compte administrateur si Windows en a demandé un autre)
$MemeCompte = ($Profil -eq $env:USERPROFILE)
$Bureau = if ($MemeCompte) { [Environment]::GetFolderPath("Desktop") } else { Join-Path $Profil "Desktop" }
$Demarrage = if ($MemeCompte) { [Environment]::GetFolderPath("Startup") } else { Join-Path $Profil "AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup" }
New-Item -ItemType Directory -Force -Path $Dossier | Out-Null
Set-Location $Dossier
function Rafraichir-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") }
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "== Python manque : installation de Python 3.12 (winget, 2 à 3 minutes)"
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Null
    Rafraichir-Path
  }
  if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Host "Python n'est pas installé : installe-le depuis https://www.python.org (coche « Add to PATH »), puis relance." -ForegroundColor Yellow
    exit 1
  }
}
# Python 3.12 de préférence (MediaPipe pour les gestes ne suit pas toujours les toutes dernières versions)
$PyVer = @()
try { $ErrorActionPreference = "Continue"; & py -3.12 -c "print(1)" 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { $PyVer = @("-3.12") } } catch { }
$ErrorActionPreference = "Stop"
Write-Host "== Arrêt d'une ancienne installation éventuelle"
Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like "*eva-satellite*satellite.py*" -or ($_.ExecutablePath -like "*eva-satellite*") } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
py @PyVer -m venv venv
$Py = Join-Path $Dossier "venv\Scripts\python.exe"
# Téléchargements par Python (OpenSSL) et non par PowerShell : Windows PowerShell 5 (Schannel / .NET) refuse souvent
# la connexion chiffrée d'EVA (« La connexion sous-jacente a été fermée »). Réseau local, premier contact : pas de vérification.
function Telecharger([string]$Url, [string]$Fichier, [switch]$Facultatif) {
  $code = "import ssl,sys,urllib.request as u; c=ssl._create_unverified_context(); d=u.urlopen(u.Request(sys.argv[1],headers={'User-Agent':'eva-installer'}),context=c,timeout=300).read(); open(sys.argv[2],'wb').write(d)"
  & $Py -c $code $Url $Fichier
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Fichier)) {
    if ($Facultatif) { Write-Host "(facultatif, ignoré : $Url)"; return }
    throw "Téléchargement impossible : $Url (EVA est-elle joignable depuis ce PC ? ouvre $Eva dans le navigateur pour vérifier)"
  }
}
Write-Host "== Certificat d'EVA"
Telecharger "$Eva/api/https/install/eva-certificat.crt" "eva-certificat.crt" -Facultatif
Write-Host "== Programme du satellite"
Telecharger "$Eva/api/public/satellite/satellite.py" "satellite.py"
Telecharger "$Eva/api/public/satellite/gestes.py" "gestes.py"
Telecharger "$Eva/api/public/satellite/desinstaller-windows.cmd" "desinstaller.cmd" -Facultatif   # pour désinstaller plus tard
if ($Gestes) {
  Write-Host "== Modèle de la main (MediaPipe, 8 Mo, servi par EVA)"
  Telecharger "$Eva/vendor/mediapipe/hand_landmarker.task" "hand_landmarker.task"
}
& $Py -m pip install -q --upgrade pip
& $Py -m pip install -q numpy sounddevice requests psutil websocket-client
if ($Eveil -eq "local") {
  Write-Host "== Mot d'éveil local (sherpa-onnx, modèle de 17 Mo)"
  & $Py -m pip install -q sherpa-onnx
  Telecharger "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2" "kws.tar.bz2"
  New-Item -ItemType Directory -Force -Path modele-eveil | Out-Null
  tar -xjf kws.tar.bz2 -C modele-eveil --strip-components=1
  Remove-Item kws.tar.bz2
}
if ($Ecran) {
  Write-Host "== Écran : capture et lecture du texte (mss, rapidocr)"
  & $Py -m pip install -q mss pillow pystray
  & $Py -m pip install -q rapidocr_onnxruntime
  if ($LASTEXITCODE -ne 0) { & $Py -m pip install -q rapidocr onnxruntime }
}
if ($Gestes) {
  Write-Host "== Gestes : caméra (mediapipe, opencv) — quelques minutes"
  & $Py -m pip install -q mediapipe opencv-python
  if ($LASTEXITCODE -ne 0) { Write-Host "MediaPipe ne s'installe pas avec cette version de Python : installe Python 3.12 puis relance." -ForegroundColor Yellow }
}
$Conf = @{ eva = $Eva; jeton = $Jeton; certificat = "eva-certificat.crt"; eveil = $Eveil }
if ($Fenetre -or $Tableau) { $Conf.fenetre = $true; & $Py -m pip install -q pillow pystray }
if ($Tableau) { $Conf.tableau = $true }
if ($Ecran) { $Conf.ecran = $true }
if ($Gestes) { $Conf.gestes = $true }
[IO.File]::WriteAllText((Join-Path $Dossier "satellite.json"), ($Conf | ConvertTo-Json))   # UTF-8 sans BOM
Write-Host "== Micros et haut-parleurs détectés :"
& $Py satellite.py --liste-audio
# Raccourcis sur le bureau : couper / rétablir l'écoute du satellite sans passer par EVA
"@echo off`r`ntype nul > `"$Dossier\pause`"`r`necho Satellite EVA en pause : il n'ecoute plus.`r`ntimeout /t 3 >nul" | Set-Content -Encoding ASCII (Join-Path $Bureau "EVA pause.cmd")
"@echo off`r`ndel `"$Dossier\pause`" 2>nul`r`necho Satellite EVA : ecoute reactivee.`r`ntimeout /t 3 >nul" | Set-Content -Encoding ASCII (Join-Path $Bureau "EVA reprise.cmd")
$Tache = "EVA Satellite"
$Lancer = "@echo off`r`ndel `"$Dossier\arrete`" 2>nul`r`nschtasks /Run /TN `"$Tache`" >nul 2>&1 || (cd /d `"$Dossier`" & start `"`" /min `"$Dossier\venv\Scripts\pythonw.exe`" satellite.py)`r`necho Satellite EVA demarre.`r`ntimeout /t 2 >nul"
$Lancer | Set-Content -Encoding ASCII (Join-Path $Bureau "EVA démarrer.cmd")
"@echo off`r`ntype nul > `"$Dossier\arrete`"`r`nschtasks /End /TN `"$Tache`" >nul 2>&1`r`npowershell -NoProfile -Command `"Get-CimInstance Win32_Process -Filter 'Name like ''python%%'' ' | Where-Object { `$_.CommandLine -like '*eva-satellite*' } | ForEach-Object { Stop-Process -Id `$_.ProcessId -Force -ErrorAction SilentlyContinue }`"`r`necho Satellite EVA arrete (raccourci EVA demarrer pour le relancer).`r`ntimeout /t 3 >nul" | Set-Content -Encoding ASCII (Join-Path $Bureau "EVA arrêter.cmd")
$AncienDemarrage = Join-Path $Demarrage "eva-satellite.cmd"
if ($Admin) {
  # Lancement à l'ouverture de session AVEC les droits administrateur (tâche planifiée « EVA Satellite », plus haut niveau)
  Remove-Item $AncienDemarrage -ErrorAction SilentlyContinue
  $Act = New-ScheduledTaskAction -Execute "$Dossier\venv\Scripts\pythonw.exe" -Argument "satellite.py" -WorkingDirectory $Dossier
  $Decl = @(New-ScheduledTaskTrigger -AtLogOn -User $Compte)
  # Gardien : toutes les 5 minutes la tâche relance le satellite s'il s'est arrêté (sans effet s'il tourne déjà)
  try { $Decl += New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) } catch { }
  $Qui = New-ScheduledTaskPrincipal -UserId $Compte -RunLevel Highest -LogonType Interactive
  $Regl = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) `
          -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
  Register-ScheduledTask -TaskName $Tache -Action $Act -Trigger $Decl -Principal $Qui -Settings $Regl -Force | Out-Null
  Start-ScheduledTask -TaskName $Tache
  Write-Host "C'est prêt : le satellite tourne (droits administrateur) et repartira à chaque ouverture de session. Dis « EVA, quelle heure est-il ? »." -ForegroundColor Green
} else {
  "@echo off`r`ncd /d `"$Dossier`"`r`nstart `"`" /min `"$Dossier\venv\Scripts\pythonw.exe`" satellite.py" | Set-Content -Encoding ASCII $AncienDemarrage
  Start-Process -WindowStyle Minimized "$Dossier\venv\Scripts\pythonw.exe" -ArgumentList "satellite.py" -WorkingDirectory $Dossier
  Write-Host "C'est prêt : le satellite tourne et se relancera à chaque ouverture de session. Dis « EVA, quelle heure est-il ? »." -ForegroundColor Green
}
Write-Host "Raccourcis sur le bureau : EVA pause, EVA reprise, EVA démarrer, EVA arrêter. Icône EVA à côté de l'horloge (clic droit)."
