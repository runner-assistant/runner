"""
clap_launcher.py - Double clap -> musique, LED Govee, voix de Runner, applis placées.

Les réglages sont dans config.json (même dossier), modifiables avec clap_config.py.

Dépendances : pip install sounddevice numpy soundfile edge-tts
  pythonw clap_launcher.py           écoute, lance tout au double clap, puis s'arrête
  python clap_launcher.py --stop     arrête la musique et la voix en cours (les LED restent)
  python clap_launcher.py --wifi     active le point d'accès Wi-Fi du PC (pour les LED)
Utilisés par la fenêtre de réglages : --config <fichier> (réglages de test), --debug.
"""

import colorsys
import ctypes
import glob
import json
import math
import os
import queue
import re
import shlex
import shutil
import base64
import builtins
import logging
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from ctypes import wintypes
from datetime import datetime, timedelta

try:
    import numpy as np
    import sounddevice as sd
except ImportError as e:                         # souvent après une mise à jour de Python
    _msg = (f"Bibliothèque manquante ({e.name}). Dans un terminal : "
            "pip install -U sounddevice numpy soundfile edge-tts")
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "runner.log"), "a",
              encoding="utf-8") as _f:
        _f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  ERROR   [démarrage]  {_msg}\n")
    raise

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_LOG = os.path.join(DOSSIER, "runner.log")
_log = logging.getLogger("runner")
MOTS_ALERTE = ("impossible", "introuvable", "échec", "indisponible", "erreur", "non trouvée",
               "aucune", "aucun micro", "refus", "pas prête", "pas encore", "pas de connexion",
               "injoignable", "non confirmé", "sans réponse")


def configurer_journal(etiquette):
    """Journal partagé runner.log (dans le dossier du projet). Chaque ligne indique qui écrit :
    [écoute] Runner en arrière-plan, [test], [réglages] la fenêtre, etc."""
    if _log.handlers:
        return
    migrer_ancien_nom()
    try:
        if os.path.getsize(FICHIER_LOG) > 1_000_000:          # au-delà de 1 Mo : on archive
            os.replace(FICHIER_LOG, os.path.join(DOSSIER, "runner.ancien.log"))
    except OSError:
        pass
    try:
        h = logging.FileHandler(FICHIER_LOG, encoding="utf-8")
    except OSError:
        return
    h.setFormatter(logging.Formatter(f"%(asctime)s  %(levelname)-7s [{etiquette}]  %(message)s",
                                     "%Y-%m-%d %H:%M:%S"))
    _log.addHandler(h)
    _log.setLevel(logging.INFO)

    def exception_non_prevue(t, v, tb):
        _log.error("Erreur non prévue", exc_info=(t, v, tb))
        sys.__excepthook__(t, v, tb)
    sys.excepthook = exception_non_prevue
    threading.excepthook = lambda a: _log.error(f"Erreur non prévue ({a.thread.name})",
                                                exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    for alerte in ALERTES_CONFIG:
        _log.warning(alerte)


def print(*args, **kw):
    """Affiche dans la console (s'il y en a une) et écrit dans le journal."""
    builtins.print(*args, **kw)
    if _log.handlers and kw.get("file") is None:
        texte = " ".join(map(str, args))
        alerte = any(m in texte.lower() for m in MOTS_ALERTE)
        _log.log(logging.WARNING if alerte else logging.INFO, texte)
FICHIER_STOP = os.path.join(tempfile.gettempdir(), "runner_stop")   # sa présence demande un arrêt
FICHIER_EN_COURS = os.path.join(tempfile.gettempdir(), "runner_en_cours")  # pid du lancement en cours
ARRET = threading.Event()           # coupe la musique et la voix
ARRET_LEDS = threading.Event()      # éteint aussi les LED (bouton Stop d'un test des LED ou complet)
SANS_FENETRE = 0x08000000           # CREATE_NO_WINDOW : commandes lancées sans console
DETACHE = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP : apps indépendantes


def powershell(script, timeout=30):
    """Exécute un script PowerShell sans fenêtre (encodé : ni guillemets ni accents à échapper)."""
    return subprocess.run(["powershell", "-NoProfile", "-NoLogo", "-NonInteractive", "-EncodedCommand",
                           base64.b64encode(script.encode("utf-16-le")).decode()],
                          capture_output=True, text=True, timeout=timeout, creationflags=SANS_FENETRE)


def ps_texte(texte):
    """Texte entre apostrophes pour PowerShell (une apostrophe s'y écrit deux fois)."""
    return "'" + str(texte).replace("'", "''") + "'"


def lancement_en_cours():
    """True si un lancement (musique…) tourne dans un autre processus."""
    try:
        with open(FICHIER_EN_COURS) as f:
            pid = int(f.read().strip())
        return pid != os.getpid() and processus_actif(pid)
    except (OSError, ValueError, NameError):
        return False


def demander_arret(leds=False):
    with open(FICHIER_STOP, "w") as f:
        f.write("tout" if leds else "musique")


def arret_demande():
    """Vrai si l'arrêt a été demandé (touche, fenêtre de réglages ou --stop). Le fichier
    d'arrêt est lu une fois puis l'événement ARRET mémorise la demande."""
    if not ARRET.is_set() and os.path.exists(FICHIER_STOP):
        try:
            with open(FICHIER_STOP) as f:
                if "tout" in f.read():
                    ARRET_LEDS.set()
        except OSError:
            pass
        ARRET.set()
    return ARRET.is_set()


def arret_leds_demande():
    arret_demande()
    return ARRET_LEDS.is_set()
FICHIER_CONFIG_REEL = os.path.join(DOSSIER, "config.json")
FICHIER_CONFIG = FICHIER_CONFIG_REEL
if "--config" in sys.argv:                       # réglages de test (non enregistrés) de clap_config.py
    FICHIER_CONFIG = sys.argv[sys.argv.index("--config") + 1]

# ======================= Réglages par défaut =======================
# (remplacés par ceux de config.json s'il existe)
DEFAUT = {
    "micro": "Réseau de microphones",
    "detection": {"attaque_min": 6.0, "decroissance_max": 0.20, "brillance_min": 0.10,
                  "fond_min": 8.0, "seuil_min": 0.02, "ecart_max": 0.80},
    "leds": {"active": True, "ip": "", "motif": "arc-en-ciel", "couleur": "#ff0000",
             "luminosite": 100, "duree": 3.0,
             # Mode rythme : à la place du motif, les LED suivent les coups de la musique
             "rythme": {"actif": False, "mode": "mono", "sensibilite": 60,
                        "avance_ms": 150,     # commandes envoyées en avance (retard des LED)
                        "eteindre_silences": True}},  # LED éteintes pendant les silences
    "voix": {"active": True, "voix": "fr-FR-HenriNeural",
             "ville": "Poitiers", "lat": 46.58, "lon": 0.34, "delai": 1.0,
             # Phrase principale : 4 parties dans cet ordre, chacune activable
             "parties": {"accueil": {"actif": True, "texte": "Bonjour Monsieur."},
                         "heure": {"actif": True, "texte": "Il est {heure}."},
                         "meteo": {"actif": True, "texte": "Il fait {temperature} degrés à {ville}, avec {ciel}."},
                         "cours": {"actif": True, "texte": "Votre prochain cours, {cours}, commence à {heure_cours}{salle}."},
                         # Mails : « texte » s'il y a plusieurs nouveaux mails, « un » pour un seul,
                         # « aucun » s'il n'y en a pas (vide = rien n'est dit)
                         "mails": {"actif": True,
                                   "texte": "Vous avez {nb_mails} nouveaux mails, dont le dernier de {expediteur}.",
                                   "un": "Vous avez un nouveau mail, de {expediteur}.",
                                   "aucun": "Aucun nouveau mail."},
                         "fin": {"actif": True, "texte": "Votre espace de travail est prêt."}},
             "secours": "Bienvenue Monsieur. Votre espace de travail est prêt."},
    "musique": {"fichier": "highway_to_hell.mp3",
                "volume_pct": 100,          # volume de la musique (%)
                "pendant_voix_pct": 35,     # musique pendant que Runner parle, en % (100 = pas de baisse)
                "jusqu_a_la_fin": True,     # sinon : arrêt après 'duree_max_s', en fondu
                "duree_max_s": 60, "fondu_fin_s": 3.0},
    "sortie_audio": "",          # "" = sortie Windows actuelle, sinon (début du) nom de la sortie
    # Emploi du temps (lien .ics) et mails : Gmail par « Se connecter avec Google », autres boîtes
    # en IMAP. Mots de passe et jetons dans le Gestionnaire d'identification de Windows,
    # jamais dans ce fichier.
    "infos": {"agenda": {"actif": False, "lien": ""},
              "mails": {"actif": False, "comptes": []},
              "ouvrir_webmail": True,       # onglet du webmail ajouté dans le navigateur
              "recap": True},               # petite fenêtre récapitulative au lancement
    "systeme": {"point_acces": True, "demarrage_session": False, "reveil": False,
                "raccourci": "ctrl+alt+r",  # déclenche Runner comme un double clap ("" = aucun)
                "attente_max": 3.0,      # s max d'attente (voix, LED) avant de tout lancer quand même
                "ecoute_max_min": 10},   # arrêt de l'écoute sans double clap (min), 0 = jamais
    "apps": [
        {"exe": r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe|%ProgramFiles%\Microsoft VS Code\Code.exe",
         "args": "",
         "ecran": "secondaire", "zone": "gauche_2tiers"},
        {"exe": r"%ProgramFiles%\Google\Chrome\Application\chrome.exe|"
                 r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe|"
                 r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
         "args": "https://www.youtube.com", "ecran": "secondaire", "zone": "droite_1tiers"},
    ],
}

# Listes proposées dans les menus de clap_config.py
ZONES = {"plein": (0, 1), "gauche_moitie": (0, .5), "droite_moitie": (.5, 1),
         "gauche_2tiers": (0, 2 / 3), "droite_1tiers": (2 / 3, 1),
         "gauche_1tiers": (0, 1 / 3), "droite_2tiers": (1 / 3, 1), "centre_1tiers": (1 / 3, 2 / 3)}
# Dispositions proposées (comme le menu d'ancrage de Windows 11)
DISPOSITIONS = [["plein"], ["gauche_moitie", "droite_moitie"], ["gauche_2tiers", "droite_1tiers"],
                ["gauche_1tiers", "droite_2tiers"], ["gauche_1tiers", "centre_1tiers", "droite_1tiers"]]
ECRANS = ["principal", "secondaire"]
MOTIFS = ["fixe", "arc-en-ciel", "pulsation", "clignotement", "fondu"]
MODES_RYTHME = {"mono": "Monochrome (couleur finale)", "couleurs": "Couleurs qui varient"}
VOIX_DISPO = ["fr-FR-HenriNeural", "fr-FR-RemyMultilingualNeural", "fr-CA-AntoineNeural",
              "fr-CH-FabriceNeural", "fr-BE-GerardNeural", "fr-FR-DeniseNeural",
              "fr-FR-VivienneMultilingualNeural", "en-US-AndrewMultilingualNeural",
              "en-US-BrianMultilingualNeural", "en-GB-RyanNeural"]
EXTENSIONS_AUDIO = (".mp3", ".wav", ".wma", ".m4a")
NAVIGATEURS = ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe")


ALERTES_CONFIG = []                               # problèmes rencontrés en lisant config.json


def ecrire_json(chemin_fichier, donnees, sauvegarde=True):
    """Écriture sûre : fichier temporaire, puis remplacement en une seule opération. Si le PC
    s'éteint en plein enregistrement, l'ancien fichier reste intact. L'ancienne version est
    gardée dans un .bak."""
    tmp = f"{chemin_fichier}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(donnees, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    if sauvegarde and os.path.exists(chemin_fichier):
        try:
            with open(chemin_fichier, encoding="utf-8") as f:
                json.load(f)                        # on ne sauvegarde en .bak qu'un fichier valide
            shutil.copyfile(chemin_fichier, chemin_fichier + ".bak")
        except (OSError, ValueError):
            pass
    for essai in range(10):                         # un antivirus peut bloquer le fichier un instant
        try:
            os.replace(tmp, chemin_fichier)
            return
        except PermissionError:
            time.sleep(0.1 * (essai + 1))
    os.replace(tmp, chemin_fichier)


def _lire_json(chemin_fichier):
    with open(chemin_fichier, encoding="utf-8") as f:
        donnees = json.load(f)
    if not isinstance(donnees, dict):
        raise ValueError("le contenu n'est pas un ensemble de réglages")
    return donnees


def _fusionner(defaut, donnees, chemin=""):
    """Reprend les valeurs du fichier dont le type correspond à celui attendu ; les autres
    sont ignorées (valeur par défaut gardée) et signalées."""
    for cle, val in donnees.items():
        nom = f"{chemin}{cle}"
        attendu = defaut.get(cle)
        if cle not in defaut:
            defaut[cle] = val                       # clé inconnue : gardée telle quelle
        elif isinstance(attendu, dict):
            if isinstance(val, dict):
                if cle == "parties":
                    defaut[cle] = val
                else:
                    _fusionner(attendu, val, nom + ".")
            else:
                ALERTES_CONFIG.append(f"Réglage « {nom} » invalide, valeur par défaut utilisée")
        elif isinstance(attendu, bool) or isinstance(val, bool):
            if isinstance(attendu, bool) and isinstance(val, bool):
                defaut[cle] = val
            else:
                ALERTES_CONFIG.append(f"Réglage « {nom} » invalide, valeur par défaut utilisée")
        elif any(isinstance(attendu, t) and isinstance(val, t) for t in ((int, float), str, list)):
            defaut[cle] = val                    # même type que la valeur par défaut : acceptée
        else:
            ALERTES_CONFIG.append(f"Réglage « {nom} » invalide, valeur par défaut utilisée")


def charger_config():
    """Réglages par défaut complétés par config.json. Fichier illisible : on essaie la copie
    .bak, sinon on part des réglages par défaut (le fichier abîmé est mis de côté)."""
    ALERTES_CONFIG.clear()
    cfg = json.loads(json.dumps(DEFAUT))          # copie profonde
    fichier = {}
    if os.path.exists(FICHIER_CONFIG):
        try:
            fichier = _lire_json(FICHIER_CONFIG)
        except (OSError, ValueError) as e:
            ALERTES_CONFIG.append(f"config.json illisible ({e})")
            try:
                fichier = _lire_json(FICHIER_CONFIG + ".bak")
                ALERTES_CONFIG.append("Réglages repris de la dernière copie valide (config.json.bak)")
            except (OSError, ValueError):
                ALERTES_CONFIG.append("Aucune copie valide : réglages par défaut utilisés")
            if FICHIER_CONFIG == FICHIER_CONFIG_REEL:
                try:
                    shutil.copyfile(FICHIER_CONFIG, os.path.join(DOSSIER, "config.illisible.json"))
                except OSError:
                    pass
    _fusionner(cfg, fichier)
    cfg["apps"] = [a for a in cfg["apps"] if isinstance(a, dict) and isinstance(a.get("exe"), str)]

    # Anciens réglages de volume (0-1000) -> pourcentages
    mu, ancien = cfg["musique"], fichier.get("musique", {}) if isinstance(fichier.get("musique"), dict) else {}
    if "volume" in ancien and "volume_pct" not in ancien:
        mu["volume_pct"] = round(ancien["volume"] / 10)
    if "volume_voix" in ancien and "pendant_voix_pct" not in ancien:
        mu["pendant_voix_pct"] = min(100, round(100 * ancien["volume_voix"] / max(1, ancien.get("volume", 1000))))
    for k in ("volume", "volume_voix"):
        mu.pop(k, None)
    # Ancienne phrase en un bloc avec {salut} {nom} : on garde le nom choisi
    v, ancienne = cfg["voix"], fichier.get("voix", {}) if isinstance(fichier.get("voix"), dict) else {}
    if "nom" in ancienne and "parties" not in ancienne:
        nom = ancienne["nom"]
        v["parties"]["accueil"]["texte"] = f"Bonjour {nom}."
        if "secours" not in ancienne:
            v["secours"] = f"Bienvenue {nom}. Votre espace de travail est prêt."
    for k in ("nom", "texte"):
        v.pop(k, None)
    for nom_partie, defaut_partie in DEFAUT["voix"]["parties"].items():   # parties manquantes
        p = v["parties"].get(nom_partie)
        if not isinstance(p, dict) or not isinstance(p.get("texte"), str):
            v["parties"][nom_partie] = dict(defaut_partie)
    m = v["parties"]["mails"]
    if m["texte"].strip() == "{mails}.":                 # ancienne phrase toute faite : modèles par défaut
        m.update({k: DEFAUT["voix"]["parties"]["mails"][k] for k in ("texte", "un", "aucun")})
    for k in ("un", "aucun"):
        if not isinstance(m.get(k), str):
            m[k] = DEFAUT["voix"]["parties"]["mails"][k]
    return cfg


def sauver_config(cfg):
    ecrire_json(FICHIER_CONFIG, cfg)


CFG = charger_config()


def chemin(fichier):
    """Chemin absolu existant, ou None. Accepte %VARIABLES%, *, les chemins relatifs au
    dossier du script et plusieurs alternatives séparées par | (la première trouvée gagne)."""
    for alt in fichier.split("|"):
        alt = os.path.expandvars(alt.strip())
        if not os.path.isabs(alt):
            alt = os.path.join(DOSSIER, alt)
        trouves = sorted(glob.glob(alt))
        if trouves:
            return trouves[-1]
    return None


def chemin_musique(fichier):
    """Retrouve la musique même si elle a été déplacée dans 'musiques' (ou en sortie)."""
    if not fichier:
        return None
    nom = os.path.basename(fichier)
    for essai in (fichier, nom, os.path.join("musiques", nom)):
        trouve = chemin(essai)
        if trouve:
            return trouve
    print(f"Musique introuvable : {fichier}")
    return None


def musiques_dispo():
    """Fichiers audio du dossier du script et de son sous-dossier 'musiques'."""
    res = []
    for sous in ("", "musiques"):
        d = os.path.join(DOSSIER, sous)
        if os.path.isdir(d):
            res += [os.path.join(sous, f) if sous else f for f in sorted(os.listdir(d))
                    if f.lower().endswith(EXTENSIONS_AUDIO)]
    return res


# --------------------------------- Audio ---------------------------------
def sorties_dispo():
    """Noms des sorties audio (sans doublons de pilotes)."""
    generiques = ("mappeur de sons", "sound mapper", "pilote audio principal", "primary sound")
    return sorted({d["name"] for d in sd.query_devices() if d["max_output_channels"]
                   and not any(g in d["name"].lower() for g in generiques)})


def choisir_sortie():
    """Index de la sortie choisie. None (auto) = « Mappeur de sons » de Windows, qui suit
    la sortie par défaut au moment où la lecture démarre."""
    nom = CFG.get("sortie_audio", "")
    if not nom:
        return None
    ordre = {"MME": 0, "Windows DirectSound": 1, "Windows WASAPI": 2}
    for i in sorted((i for i, d in enumerate(sd.query_devices())
                     if d["max_output_channels"] and nom.lower()[:25] in d["name"].lower()),
                    key=lambda i: ordre.get(sd.query_hostapis(sd.query_devices(i)["hostapi"])["name"], 9)):
        try:
            sd.check_output_settings(device=i, samplerate=44100)
            return i
        except Exception:
            pass
    print(f"Sortie audio « {nom} » indisponible, sortie Windows utilisée")
    return None


class _EnMemoire:
    """Fichier audio court (voix) chargé entièrement en mémoire : le fichier n'est pas gardé
    ouvert pendant la lecture, il peut donc être remplacé à tout moment par un autre processus."""

    def __init__(self, fichier):
        import soundfile as sf
        self.donnees, self.samplerate = sf.read(fichier, dtype="float32", always_2d=True)
        self.channels, self.pos = self.donnees.shape[1], 0

    def read(self, n, dtype=None, always_2d=True):
        bloc = self.donnees[self.pos:self.pos + n]
        self.pos += len(bloc)
        return bloc

    def close(self):
        pass


class Lecteur:
    """Lit un fichier audio (mp3, wav…) sur la sortie choisie. Le volume se règle en direct
    avec regler(), en fondu progressif (pas de saut brutal)."""
    FONDU = 0.6          # s pour passer de 0 à 100 % de volume

    def __init__(self, fichier, volume=1.0):
        import soundfile as sf
        if os.path.getsize(fichier) < 8_000_000:
            self.f = _EnMemoire(fichier)
        else:                                    # longue musique : lue au fil de l'eau
            self.f = sf.SoundFile(fichier)
        self.volume = self.cible = volume
        self.vitesse, self.position, self.en_fin = self.FONDU, 0, False
        self.fini = threading.Event()
        self.flux = sd.OutputStream(samplerate=self.f.samplerate, channels=self.f.channels,
                                    device=choisir_sortie(), dtype="float32",
                                    callback=self._remplir, finished_callback=self.fini.set)

    def regler(self, volume, fondu=None):
        """Change le volume en fondu ; 'fondu' : durée en s pour y arriver (sinon vitesse normale).
        Sans effet pendant le fondu de fin (la voix ne doit pas faire remonter la musique)."""
        if self.en_fin:
            return
        ecart = abs(volume - self.volume)
        self.vitesse = (fondu / ecart) if fondu and ecart > 0.001 else self.FONDU
        self.cible = volume

    def fondu_de_fin(self, duree, stop=lambda: False):
        """Baisse progressivement jusqu'au silence, puis arrête la lecture."""
        if duree > 0 and not self.fini.is_set():
            self.regler(0, duree)
            self.en_fin = True
            fin = time.time() + duree + 0.2
            while time.time() < fin and not self.fini.is_set() and not stop():
                time.sleep(0.05)
        self.arreter()

    def temps_entendu(self):
        """Position de lecture réellement audible (s) : échantillons envoyés à la carte son,
        moins sa latence de sortie."""
        latence = getattr(self.flux, "latency", 0.1)
        return self.position / self.f.samplerate - (latence if isinstance(latence, float) else 0.1)

    def _remplir(self, sortie, n, *_):
        data = self.f.read(n, dtype="float32", always_2d=True)
        k = len(data)
        self.position += k
        if k and self.volume != self.cible:            # rampe de volume, échantillon par échantillon
            pas = 1 / (self.vitesse * self.f.samplerate)
            ecart = self.cible - self.volume
            rampe = self.volume + np.sign(ecart) * pas * np.arange(1, k + 1)
            rampe = np.minimum(rampe, self.cible) if ecart > 0 else np.maximum(rampe, self.cible)
            self.volume = float(rampe[-1])
            sortie[:k] = data * rampe[:, None]
        else:
            sortie[:k] = data * self.volume
        if k < n:
            sortie[len(data):] = 0
            raise sd.CallbackStop

    def jouer(self):
        self.flux.start()
        return self

    def attendre(self, stop=lambda: False, fondu_si_stop=0.6):
        """Attend la fin ; si 'stop()' devient vrai, coupe avec un court fondu."""
        while not self.fini.wait(0.2):
            if stop():
                self.fondu_de_fin(fondu_si_stop)
                break
        self.arreter()

    def arreter(self):
        try:
            self.flux.abort()
            self.flux.close()
            self.f.close()
        except Exception:
            pass
        self.fini.set()


_musique = {"lecteur": None}


def surveiller_musique(lecteur):
    """Arrête la musique en fondu : à la demande (clavier, --stop, Stop), ou après la durée
    choisie si « jusqu'à la fin » est décoché."""
    mu, debut = CFG["musique"], time.time()
    limite = None if mu.get("jusqu_a_la_fin", True) else float(mu.get("duree_max_s", 60))
    temps_ecoule = lambda: limite is not None and time.time() - debut >= limite
    while not lecteur.fini.wait(0.2) and not arret_demande() and not temps_ecoule():
        pass
    if arret_demande():
        lecteur.fondu_de_fin(0.6)
    elif temps_ecoule() and not lecteur.fini.is_set():
        print(f"Musique arrêtée après {limite:g} s")
        lecteur.fondu_de_fin(float(mu.get("fondu_fin_s", 3)), arret_demande)
    lecteur.arreter()


def touches_d_arret():
    """Pendant la musique, ces touches l'arrêtent depuis n'importe où : touches multimédia
    Lecture/Pause et Stop du clavier, ou Ctrl+Alt+M."""
    raccourcis = [(0, 0xB2), (0, 0xB3), (0x0001 | 0x0002 | 0x4000, ord("M"))]   # Stop, Lecture/Pause, Ctrl+Alt+M
    for i, (modif, touche) in enumerate(raccourcis, start=1):
        user32.RegisterHotKey(None, i, modif, touche)     # ignoré si une autre app les utilise déjà
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        if msg.message == 0x0312:                         # WM_HOTKEY
            print("Musique arrêtée au clavier")
            ARRET.set()
            break
    for i in range(1, len(raccourcis) + 1):
        user32.UnregisterHotKey(None, i)


RACCOURCIS = {"": "(aucun)", "ctrl+alt+r": "Ctrl + Alt + R", "ctrl+alt+espace": "Ctrl + Alt + Espace",
              "ctrl+maj+r": "Ctrl + Maj + R", "win+alt+r": "Win + Alt + R", "ctrl+alt+f12": "Ctrl + Alt + F12"}
DECLENCHE = threading.Event()        # raccourci clavier pressé : comme un double clap


def touches_raccourci(texte):
    """'ctrl+alt+r' -> (modificateurs, touche) pour RegisterHotKey, ou None."""
    mods, touche = 0, None
    for p in texte.lower().replace(" ", "").split("+"):
        if p in ("ctrl", "alt", "maj", "shift", "win"):
            mods |= {"alt": 1, "ctrl": 2, "maj": 4, "shift": 4, "win": 8}[p]
        elif p == "espace":
            touche = 0x20
        elif re.fullmatch(r"f([1-9]|1[0-2])", p):
            touche = 0x6F + int(p[1:])
        elif re.fullmatch(r"[a-z0-9]", p):
            touche = ord(p.upper())
    return (mods, touche) if mods and touche else None


def ecouter_raccourci():
    """Enregistre le raccourci global qui déclenche Runner. True s'il est actif."""
    texte = CFG["systeme"].get("raccourci", "")
    combo = touches_raccourci(texte)
    if not combo:
        return False
    pret, res = threading.Event(), {}

    def boucle():                                # le raccourci appartient à ce fil
        res["ok"] = bool(user32.RegisterHotKey(None, 100, combo[0] | 0x4000, combo[1]))   # sans répétition
        pret.set()
        msg = wintypes.MSG()
        while res["ok"] and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312 and msg.wParam == 100:
                if ecoute_en_pause():
                    print("Raccourci ignoré : un test est en cours")
                else:
                    DECLENCHE.set()

    threading.Thread(target=boucle, daemon=True).start()
    pret.wait(2)
    nom = RACCOURCIS.get(texte, texte)
    if res.get("ok"):
        print(f"Raccourci {nom} actif")
    else:
        print(f"Raccourci {nom} indisponible : déjà utilisé par une autre application (ou par Runner en arrière-plan)")
    return res.get("ok", False)


# ------------------------------- LED Govee -------------------------------
def chercher_leds(delai=1.5):
    """Requête 'scan' Govee (multicast + broadcast sur chaque carte réseau) -> {ip: modèle}.
    S'arrête 0,3 s après la dernière réponse au lieu d'attendre tout le délai."""
    rep = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rep.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        rep.bind(("", 4002))
    except OSError:
        rep.close()
        return {}
    rep.settimeout(0.1)
    msg = b'{"msg":{"cmd":"scan","data":{"account_topic":"reserve"}}}'
    for ip in {i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as env:
                env.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                env.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip))
                env.bind((ip, 0))
                for dest in ("239.255.255.250", "255.255.255.255", ip.rsplit(".", 1)[0] + ".255"):
                    env.sendto(msg, (dest, 4001))
        except OSError:
            pass
    trouvees, fin = {}, time.time() + delai
    while time.time() < fin:
        try:
            d = json.loads(rep.recvfrom(4096)[0])["msg"]["data"]
            trouvees[d["ip"]] = d.get("sku", "?")
            fin = min(fin, time.time() + 0.3)
        except (TimeoutError, ValueError, KeyError, OSError):
            pass
    rep.close()
    return trouvees


def hex_rgb(h):
    """'#rrggbb' -> (r, g, b) en 0-255."""
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def commande_govee(cmd, valeur):
    """Message UDP de l'API LAN Govee. 'turn' et 'brightness' : un nombre ; 'colorwc' : (r, g, b)."""
    if cmd in ("turn", "brightness"):
        data = {"value": int(valeur)}
    elif cmd == "colorwc":
        data = {"color": dict(zip("rgb", map(int, valeur))), "colorTemInKelvin": 0}
    else:
        data = valeur
    return json.dumps({"msg": {"cmd": cmd, "data": data}}).encode()


def etat_led(ip, delai=0.8):
    """État réel d'une LED (commande 'devStatus' de l'API LAN) : {'onOff', 'brightness',
    'color'…}, ou None si elle ne répond pas."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as rep:
            rep.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            rep.bind(("", 4002))
            rep.settimeout(delai)
            rep.sendto(b'{"msg":{"cmd":"devStatus","data":{}}}', (ip, 4003))
            fin = time.time() + delai
            while time.time() < fin:
                donnees, (expediteur, _) = rep.recvfrom(4096)
                if expediteur == ip:
                    msg = json.loads(donnees).get("msg", {})
                    if msg.get("cmd") == "devStatus":
                        return msg.get("data", {})
    except (TimeoutError, OSError, ValueError):
        pass
    return None


def led_repond(ip, delai=0.8):
    return etat_led(ip, delai) is not None


def memoriser_ip_leds(ip):
    """Enregistre l'adresse trouvée dans config.json, pour les prochains lancements."""
    CFG["leds"]["ip"] = ip
    try:
        with open(FICHIER_CONFIG_REEL, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        cfg = {}
    except (OSError, ValueError):
        return                                      # config illisible : on n'y touche pas
    if not isinstance(cfg, dict):
        return
    if not isinstance(cfg.get("leds"), dict):
        cfg["leds"] = {}
    cfg["leds"]["ip"] = ip
    ecrire_json(FICHIER_CONFIG_REEL, cfg)


def trouver_leds():
    """(adresses, confirmées) : l'adresse mémorisée si elle répond, sinon une nouvelle
    recherche (et mémorisation). Si rien ne répond : l'ancienne adresse, non confirmée."""
    ip = CFG["leds"]["ip"]
    if ip and led_repond(ip):
        return [ip], True
    trouvees = list(chercher_leds())
    if trouvees:
        if trouvees[0] != ip:
            print(f"LED : nouvelle adresse {trouvees[0]}")
            memoriser_ip_leds(trouvees[0])
        return trouvees, True
    return ([ip] if ip else []), False


_leds = {"ips": []}


def eteindre_leds(ips=None):
    """Éteint les LED (deux envois : l'UDP ne garantit pas la réception)."""
    ips = ips or _leds["ips"] or ([CFG["leds"]["ip"]] if CFG["leds"]["ip"] else [])
    eteint = commande_govee("turn", 0)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        for _ in range(2):
            for ip in ips:
                s.sendto(eteint, (ip, 4003))
            time.sleep(0.1)


def animer_leds(ips=None, confirmees=None, motif=None):
    """Animation d'allumage (motif choisi) puis couleur et luminosité finales, vérifiées auprès
    des LED. 'ips' / 'confirmees' : déjà trouvées par l'appelant (sinon recherche ici)."""
    c = CFG["leds"]
    if not c["active"]:
        return
    if ips is None:
        ips, confirmees = trouver_leds()
    _leds["ips"] = ips
    if not ips:
        print("LED : aucune trouvée (LAN Control activé ? même réseau ? pare-feu ?)")
        return
    if confirmees is False:
        print(f"LED : sans réponse à {', '.join(ips)}, commandes envoyées quand même "
              "(LED pas encore connectées au point d'accès, ou réponses bloquées par le pare-feu ?)")
    final, lum_max, duree = hex_rgb(c["couleur"]), int(c["luminosite"]), float(c["duree"])
    motif = motif or c["motif"]

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        def envoyer(cmd, valeur):
            m = commande_govee(cmd, valeur)
            for ip in ips:
                s.sendto(m, (ip, 4003))

        def couleur(rgb):
            envoyer("colorwc", rgb)

        def lum(v):
            envoyer("brightness", max(1, min(100, round(v))))

        def etapes(pas=0.1):                 # progression de 0 à 1 pendant 'duree' secondes
            t0, i = time.time(), 0
            while (e := time.time() - t0) < duree and not arret_leds_demande():
                yield i, e / duree
                i += 1
                time.sleep(pas)

        envoyer("turn", 1)            # les LED ignorent parfois des commandes trop
        time.sleep(0.15)                         # rapprochées : on les espace un peu
        lum(1 if motif == "fondu" else lum_max)
        time.sleep(0.15)
        if motif == "arc-en-ciel":           # 2 tours, finit sur la teinte de départ
            h0 = colorsys.rgb_to_hsv(*(x / 255 for x in final))[0]
            for _, p in etapes():
                couleur(x * 255 for x in colorsys.hsv_to_rgb((h0 + 2 * p) % 1, 1, 1))
        elif motif == "pulsation":           # 3 battements de luminosité
            couleur(final)
            for _, p in etapes():
                lum(lum_max * (0.55 + 0.45 * math.cos(p * 6 * math.pi)))
        elif motif == "clignotement":
            couleur(final)
            for i, _ in etapes(0.25):
                lum(lum_max if i % 2 else 1)
        elif motif == "fondu":               # du noir vers la couleur (par la luminosité :
            couleur(final)                   # les Govee ignorent une couleur assombrie)
            for _, p in etapes():
                lum(1 + (lum_max - 1) * p)

        if arret_leds_demande():
            envoyer("turn", 0)
            return
        # État final, puis vérification auprès des LED (l'UDP ne garantit pas la réception) :
        # jusqu'à 3 essais, et une alerte dans le journal si ce n'est pas confirmé.
        def conforme(e):
            if not e or e.get("onOff") != 1:
                return False
            rgb = e.get("color") or {}
            return all(abs(int(rgb.get(k, -99)) - v) <= 3 for k, v in zip("rgb", final))

        etats = {}
        for _ in range(3):
            envoyer("turn", 1)
            time.sleep(0.15)
            couleur(final)
            time.sleep(0.15)
            lum(lum_max)
            time.sleep(0.4)
            etats = {ip: etat_led(ip) for ip in ips}
            if all(conforme(e) for e in etats.values()):
                print(f"LED confirmées : allumées en {c['couleur']} à {lum_max} % ({', '.join(ips)})")
                return
            if all(e is None for e in etats.values()):
                break                            # aucune réponse : inutile d'insister
    sans_reponse = [ip for ip, e in etats.items() if e is None]
    if sans_reponse:
        print(f"LED : état non confirmé, sans réponse de {', '.join(sans_reponse)} "
              "(si elles se sont quand même allumées : réponses bloquées par le pare-feu)")
    else:
        print(f"LED : état non confirmé après 3 essais (état lu : {etats})")


# ------------------------- Rythme (préchargé) ----------------------------
# Le morceau est analysé une fois pour toutes (quelques secondes) : instants des attaques
# (guitare, caisse claire, grosse caisse… sur tout le spectre) avec leur force, et niveau sonore.
# Le résultat est gardé dans cache_rythme/. Pendant la lecture, il n'y a plus rien à calculer :
# les commandes sont envoyées au bon moment, en avance pour compenser le retard des LED.
DOSSIER_CACHE = os.path.join(DOSSIER, "cache_rythme")
VERSION_ANALYSE = 3
CMD_PAR_S = 6                                    # commandes LED par seconde, au maximum


def fichier_analyse(musique):
    st = os.stat(musique)
    cle = re.sub(r"[^\w.-]", "_", f"{os.path.basename(musique)}-{st.st_size}-{int(st.st_mtime)}")
    return os.path.join(DOSSIER_CACHE, f"{cle}.v{VERSION_ANALYSE}.json")


def etat_prechargement(musique):
    """'pret', 'en_cours' ou 'absent'."""
    try:
        cache = fichier_analyse(musique)
    except OSError:
        return "absent"
    if os.path.exists(cache):
        return "pret"
    verrou = cache + ".verrou"
    if os.path.exists(verrou) and time.time() - os.path.getmtime(verrou) < 300:
        return "en_cours"
    return "absent"


def analyser_rythme(musique):
    """Analyse complète d'un morceau (quelques secondes) : instants et force des attaques,
    niveau sonore, passages calmes et silences. Résultat écrit dans cache_rythme/."""
    import soundfile as sf
    x, sr = sf.read(musique, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    while sr > 30000:                            # 22 kHz suffisent pour repérer les attaques
        x = x[:len(x) // 2 * 2].reshape(-1, 2).mean(axis=1)
        sr //= 2
    n, hop = 1024, 256                           # trames de ~46 ms, toutes les ~12 ms
    nb = max(0, 1 + (len(x) - n) // hop)
    fenetre = np.hanning(n).astype(np.float32)
    freqs = np.fft.rfftfreq(n, 1 / sr)
    bande, basses = (freqs >= 40) & (freqs <= 8000), (freqs >= 30) & (freqs <= 200)
    flux, flux_bas = np.zeros(nb, np.float32), np.zeros(nb, np.float32)
    rms, avant = np.zeros(nb, np.float32), None
    for d in range(0, nb, 2048):                 # par paquets (mémoire limitée)
        idx = np.arange(d, min(nb, d + 2048))
        trames = x[idx[:, None] * hop + np.arange(n)]
        rms[idx] = np.sqrt((trames ** 2).mean(axis=1))
        spec = np.log1p(100 * np.abs(np.fft.rfft(trames * fenetre, axis=1)))
        prec = np.vstack([spec[:1] if avant is None else avant, spec[:-1]])
        apparu = np.maximum(spec - prec, 0)               # « flux spectral » : ce qui apparaît
        flux[idx] = apparu[:, bande].sum(axis=1)          # tout le spectre (guitare, caisse claire…)
        flux_bas[idx] = apparu[:, basses].sum(axis=1)     # les basses seules (grosse caisse, basse)
        avant = spec[-1:]
    fps = sr / hop
    temps = (np.arange(nb) * hop + n / 2) / sr

    def moyenne_glissante(v, demi):
        c = np.concatenate([[0], np.cumsum(v, dtype=np.float64)])
        i = np.arange(len(v))
        lo, hi = np.maximum(0, i - demi), np.minimum(len(v), i + demi + 1)
        return (c[hi] - c[lo]) / (hi - lo)

    from numpy.lib.stride_tricks import sliding_window_view
    # Les basses ont peu de place dans le spectre : on les remet à égalité avant de combiner
    norme = lambda v: v / (np.percentile(v, 99) or 1)
    flux = np.maximum(norme(flux), norme(flux_bas))
    fond = moyenne_glissante(flux, int(0.4 * fps))           # niveau « habituel » autour
    v = int(0.05 * fps)
    maxi_local = sliding_window_view(np.pad(flux, v, mode="edge"), 2 * v + 1).max(axis=1)
    pics = np.flatnonzero((flux == maxi_local) & (flux > fond * 1.15) & (flux > 0.02 * flux.max()))
    exces = flux[pics] - fond[pics]
    # Force d'une attaque : comparée aux attaques voisines (±4 s) ET à tout le morceau, pour
    # qu'une intro calme garde ses accords bien marqués sans que le bruit d'un silence ressorte
    ref_globale = np.percentile(exces, 95) if len(exces) else 1
    t_pics = temps[pics]
    ref_locale = np.array([np.percentile(exces[(t_pics > t - 4) & (t_pics < t + 4)], 90) for t in t_pics])
    forces = np.clip(exces / np.maximum(ref_locale, 0.35 * ref_globale), 0, 1) if len(exces) else exces

    lisse = moyenne_glissante(rms, int(0.1 * fps))
    lisse = np.clip(lisse / (np.percentile(lisse, 95) or 1), 0, 1)
    t10 = np.arange(0, len(x) / sr, 0.1)                 # exactement 10 valeurs par seconde
    niveau = np.interp(t10, temps, lisse) if nb else np.zeros(0)
    return {"version": VERSION_ANALYSE, "duree": round(len(x) / sr, 2),
            "attaques": [[round(float(t), 3), round(float(f), 3)] for t, f in zip(t_pics, forces)],
            "niveau_10hz": [round(float(l), 3) for l in niveau]}


def precharger_rythme(musique):
    """Analyse le morceau s'il ne l'a pas déjà été (un seul processus à la fois)."""
    cache = fichier_analyse(musique)
    if os.path.exists(cache):
        return True
    os.makedirs(DOSSIER_CACHE, exist_ok=True)
    with _Verrou(cache, attente=300):
        if os.path.exists(cache):                # fait entre-temps par un autre processus
            return True
        nom = os.path.basename(musique)
        print(f"Préchargement du rythme : analyse de « {nom} »…")
        debut = time.time()
        try:
            analyse = analyser_rythme(musique)
        except Exception as e:
            print(f"Préchargement du rythme impossible pour « {nom} » : {e}")
            return False
        ecrire_json(cache, analyse, sauvegarde=False)
        nettoyer_cache(cache)
        print(f"Préchargement du rythme terminé en {time.time() - debut:.1f} s : "
              f"{len(analyse['attaques'])} attaques repérées dans « {nom} »")
    return True


def nettoyer_cache(garder):
    """Supprime les analyses périmées : ancienne version de l'analyse, ou ancienne version du
    même fichier audio (modifié ou remplacé). Les analyses des autres musiques sont gardées."""
    nom = os.path.basename(garder).rsplit("-", 2)[0]
    for f in glob.glob(os.path.join(DOSSIER_CACHE, "*.json")):
        perimee = not f.endswith(f".v{VERSION_ANALYSE}.json") or os.path.basename(f).rsplit("-", 2)[0] == nom
        if perimee and os.path.normcase(f) != os.path.normcase(garder):
            try:
                os.remove(f)
            except OSError:
                pass


def programme_leds(analyse, c):
    """Liste triée (instant, commande, données) à envoyer aux LED. L'intensité passe par la
    commande de LUMINOSITÉ (les Govee ignorent une couleur assombrie). Au plus CMD_PAR_S commandes
    par seconde :
      - les attaques les plus fortes, espacées d'au moins deux créneaux, ont chacune un flash au
        maximum puis une retombée au minimum (tout ou rien : le contrôleur lisse déjà beaucoup) ;
      - pendant les silences, LED éteintes (ou luminosité minimum), rallumées juste avant le coup ;
      - en mode « couleurs », la teinte change pendant que les LED sont sombres.
    Calculé au lancement : couleur, mode, sensibilité et avance ne demandent pas de nouvelle analyse."""
    r = c.get("rythme", {})
    final, mode, maxi = hex_rgb(c["couleur"]), r.get("mode", "mono"), int(c["luminosite"])
    seuil = 0.5 * (1 - float(r.get("sensibilite", 60)) / 100)   # attaques plus faibles ignorées
    eteindre = r.get("eteindre_silences", True)
    ecart = 1 / CMD_PAR_S
    niveaux = analyse["niveau_10hz"] or [0.5]
    # « Blanc » : quasi silence, ou creux net par rapport au niveau des 2 s autour (riff qui s'arrête)
    autour = [max(niveaux[max(0, k - 20):k + 21]) for k in range(len(niveaux))]
    blanc = [n < 0.06 or n < 0.18 * m for n, m in zip(niveaux, autour)]
    calme = lambda t: blanc[min(len(blanc) - 1, max(0, int(round(t * 10))))]
    lum = lambda x: max(1, min(100, round(x * maxi / 100)))
    teinte = colorsys.rgb_to_hsv(*(x / 255 for x in final))[0]

    # Silences d'au moins 0,4 s : [début, fin[
    silences, debut = [], None
    for k in range(len(niveaux) + 1):
        if k < len(niveaux) and blanc[k]:
            debut = k / 10 if debut is None else debut
        else:
            if debut is not None and k / 10 - debut >= 0.4:
                silences.append((debut, k / 10))
            debut = None

    # Attaques retenues : les plus fortes d'abord, jamais deux à moins de deux créneaux
    sonores = [(t, f) for t, f in analyse["attaques"]
               if f >= seuil and not all(calme(t + d) for d in (0.05, 0.15, 0.25))]
    groupes = []                                 # attaques collées (< 80 ms) : une seule, au début
    for t, f in sorted(sonores):
        if groupes and t - groupes[-1][0] < 0.08:
            groupes[-1][1] = max(groupes[-1][1], f)
        else:
            groupes.append([t, f])
    coups = []
    for t, f in sorted(groupes, key=lambda a: -a[1]):
        if all(abs(t - u) >= 2 * ecart - 1e-6 for u, _ in coups):
            coups.append((t, f))
    coups.sort()

    def series(liste):
        """Regroupe les coups séparés de moins de deux créneaux (séries rapides)."""
        res = []
        for t, f in liste:
            if res and t - res[-1][-1][0] < 2 * ecart - 1e-6:
                res[-1].append((t, f))
            else:
                res.append([(t, f)])
        return res

    # Séries rapides : un coup fort trop proche du précédent (entre 1 et 2 créneaux) est ajouté
    # s'il forme une série courte (3 coups au plus) ; elle sera rendue fort / moins fort / fort.
    for t, f in sorted(groupes, key=lambda a: -a[1]):
        if f < max(seuil, 0.6) or any(abs(t - u) < ecart - 1e-6 for u, _ in coups):
            continue
        essai = sorted(coups + [(t, f)])
        if all(len(s) <= 3 for s in series(essai) if any(abs(u - t) < 1e-6 for u, _ in s)):
            coups = essai

    pris = []                                    # instants déjà occupés
    libre = lambda t: all(abs(t - u) >= ecart - 1e-6 for u in pris)
    prog = []

    def ajouter(t, cmd, val):
        prog.append((t, cmd, val))
        pris.append(t)

    groupes_coups = series(coups)                # 1. flashs forts + retombée
    retombees = {}                               # dernier coup d'une série -> instant de retombée
    for n, serie in enumerate(groupes_coups):
        for k, (t, _force) in enumerate(serie):
            # Tout ou rien : le contrôleur Govee lisse déjà beaucoup les variations
            val = lum(100 if (len(serie) - 1 - k) % 2 == 0 else 30)   # série : fort / faible / fort
            ajouter(t, "brightness", val)
        fin = serie[-1][0]
        suivant = groupes_coups[n + 1][0][0] if n + 1 < len(groupes_coups) else analyse["duree"]
        # Flash tenu deux créneaux quand il y a la place : les LED atteignent leur plein éclat
        tenue = 2 * ecart if suivant - fin >= 4 * ecart - 1e-6 and not calme(fin + ecart) else ecart
        r = fin + tenue
        ajouter(r, "brightness", 1)
        retombees[fin] = r

    def remplacer(t, cmd, val):
        for k, x in enumerate(prog):
            if abs(x[0] - t) < 1e-6:
                prog[k] = (t, cmd, val)

    eteintes = []                                # 2. extinction pendant les silences
    if eteindre:
        for a, b in silences:
            avant = [t for t in retombees if t < a]
            suivant = next((t for t, _ in coups if t > a), None)
            retombee = retombees[max(avant)] if avant else None
            if retombee is not None and retombee < b and a - retombee <= 0.4:
                # Le silence suit un coup : extinction directe à la place de la retombée (fondu
                # naturel des Govee). Elles gardent la luminosité du flash : rallumées un peu
                # avant le coup suivant, le flash suit pile sur le coup.
                rallume = None
                if suivant is not None:
                    rallume = next((u for u in (suivant - ecart, suivant - 2 * ecart)
                                    if u >= retombee + ecart - 1e-6 and libre(u)), None)
                    if rallume is None:
                        continue                 # pas la place : simple retombée, sans extinction
                remplacer(retombee, "turn", 0)
                if rallume is not None:
                    ajouter(rallume, "turn", 1)
                eteintes.append((retombee, rallume if rallume is not None else float("inf")))
                continue
            # Silence après un passage sans coup (LED déjà basses) : extinction au début du
            # silence, rallumage au minimum juste avant le coup suivant, puis flash
            arret = next((a + k * ecart / 2 for k in range(8) if libre(a + k * ecart / 2)), None)
            rallume = (suivant - ecart) if suivant is not None else None
            if arret is None or arret >= b or (rallume is not None and
                                               (rallume < arret + ecart or not libre(rallume))):
                ajouter(a, "brightness", 1) if libre(a) else None
                continue
            ajouter(arret, "turn", 0)
            eteintes.append((arret, rallume if rallume is not None else float("inf")))
            if rallume is not None:
                ajouter(rallume, "turn", 1)
    else:
        for a, _fin in silences:
            if libre(a):
                ajouter(a, "brightness", 1)
    eteint = lambda t: any(a <= t <= b for a, b in eteintes)

    if mode == "couleurs":                       # 3. nouvelle teinte pendant que c'est sombre
        for i, (t, f) in enumerate(coups):
            tc = t + 2 * ecart
            suivant = coups[i + 1][0] if i + 1 < len(coups) else analyse["duree"]
            if f > 0.35 and suivant - t >= 3 * ecart and libre(tc) and not eteint(tc):
                teinte = (teinte + 0.13) % 1
                ajouter(tc, "colorwc", tuple(round(x * 255) for x in colorsys.hsv_to_rgb(teinte, 1, 1)))

    # Première fois que les LED s'allument : au premier coup, couleur et luminosité déjà prêtes
    if not coups:
        return []
    premier = coups[0][0]
    prog = [x for x in prog if x[0] >= premier]
    couleur0 = final if mode != "couleurs" else tuple(
        round(x * 255) for x in colorsys.hsv_to_rgb(colorsys.rgb_to_hsv(*(x / 255 for x in final))[0], 1, 1))
    # LED éteintes : couleur réglée avant, allumage en fondu montant, flash sur le coup
    pas = min(ecart, premier / 2)                # (morceau qui démarre tout de suite : plus serré)
    allumage = [(premier - 2 * pas, "colorwc", couleur0), (premier - pas, "turn", 1)]
    prog = allumage + prog
    return sorted(prog, key=lambda x: x[0])


def rythme_leds(lecteur, ips, musique):
    """Envoie le programme préchargé, calé sur la position de lecture réellement entendue."""
    c = CFG["leds"]
    try:
        with open(fichier_analyse(musique), encoding="utf-8") as f:
            analyse = json.load(f)
    except (OSError, ValueError):
        print("LED : rythme non préchargé pour cette musique, mode rythme ignoré")
        return False
    prog = programme_leds(analyse, c)
    avance = float(c.get("rythme", {}).get("avance_ms", 150)) / 1000
    final = hex_rgb(c["couleur"])
    print(f"LED : rythme préchargé, {len(prog)} commandes ({MODES_RYTHME.get(c['rythme'].get('mode'), '')})")
    message = commande_govee
    prog = [(t, cmd, message(cmd, val)) for t, cmd, val in prog]     # prêts à partir
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        def envoyer(m):
            for ip in ips:
                s.sendto(m, (ip, 4003))

        envoyer(message("turn", 0))              # éteintes jusqu'au premier coup
        i = 0
        while i < len(prog) and not lecteur.fini.is_set() and not arret_leds_demande():
            t = lecteur.temps_entendu() + avance
            while i < len(prog) and prog[i][0] <= t:
                # Une commande de luminosité trop en retard est sautée (pas l'allumage ni la couleur)
                if prog[i][1] != "brightness" or t - prog[i][0] < 0.25 or i + 1 == len(prog) \
                        or prog[i + 1][0] > t:
                    envoyer(prog[i][2])
                i += 1
            time.sleep(0.005 if i < len(prog) and prog[i][0] - t < 0.02 else 0.01)
        while not lecteur.fini.wait(0.2) and not arret_leds_demande():
            pass                                 # programme terminé : on attend la fin du morceau
        if arret_leds_demande():
            envoyer(message("turn", 0))
        else:                                    # fin de la musique : couleur et luminosité finales
            for _ in range(2):
                envoyer(message("turn", 1))
                time.sleep(0.2)
                envoyer(message("colorwc", final))
                time.sleep(0.2)
                envoyer(message("brightness", int(c["luminosite"])))
                time.sleep(0.2)
    return True


# --------------------------------- Voix ----------------------------------
METEO = {0: "un ciel dégagé", 1: "un ciel dégagé", 2: "quelques nuages", 3: "un ciel couvert",
         40: "du brouillard", 50: "de la bruine", 60: "de la pluie", 70: "de la neige",
         80: "des averses", 90: "de l'orage"}
_meteo = {"t": 0, "cle": None, "val": None}


def meteo():
    """(température, code WMO) via Open-Meteo (cache 15 min), ou None."""
    v = CFG["voix"]
    cle = (v["lat"], v["lon"])
    if time.time() - _meteo["t"] < 900 and _meteo["cle"] == cle:
        return _meteo["val"]
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={v['lat']}&longitude={v['lon']}"
           "&current=temperature_2m,weather_code")
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            c = json.load(r)["current"]
        val = round(c["temperature_2m"]), int(c["weather_code"])
    except Exception:
        val = None
    _meteo.update(t=time.time(), cle=cle, val=val)
    return val


def geocoder(ville):
    """(lat, lon) d'une ville via Open-Meteo, ou None."""
    url = ("https://geocoding-api.open-meteo.com/v1/search?count=1&language=fr&name="
           + urllib.parse.quote(ville))
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            res = json.load(r)["results"][0]
        return res["latitude"], res["longitude"]
    except Exception:
        return None

# ------------------------- Emploi du temps & mails -------------------------
def dire_heure(dt):
    """« 8 heures 15 », « midi », « minuit »… (pour la voix)."""
    h = {0: "minuit", 12: "midi"}.get(dt.hour, f"{dt.hour} heure{'s' if dt.hour > 1 else ''}")
    return h + (f" {dt.minute}" if dt.minute else "")


def _cache(nom):
    return os.path.join(tempfile.gettempdir(), f"runner_{nom}")


def lire_ics(texte):
    """Événements d'un calendrier .ics : [(début, fin, titre, lieu)] en heure locale, triés.
    Lecture simple (les exports ADE listent chaque cours, sans règle de répétition)."""
    lignes = re.sub(r"\r?\n[ \t]", "", texte).splitlines()       # lignes repliées -> une seule

    def date(valeur, params):
        valeur = valeur.strip()
        if len(valeur) == 8:                                    # journée entière
            return datetime.strptime(valeur, "%Y%m%d")
        d = datetime.strptime(valeur[:15], "%Y%m%dT%H%M%S")
        if valeur.endswith("Z"):                                # UTC -> heure locale
            from datetime import timezone
            d = d.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
        return d

    def propre(t):
        return re.sub(r"\\([,;\\])", r"\1", t).replace("\\n", " ").replace("\\N", " ").strip()

    evenements, ev = [], None
    for ligne in lignes:
        if ligne == "BEGIN:VEVENT":
            ev = {}
        elif ligne == "END:VEVENT" and ev is not None:
            if "debut" in ev:
                evenements.append((ev["debut"], ev.get("fin", ev["debut"]), ev.get("titre", "Cours"),
                                   ev.get("lieu", "")))
            ev = None
        elif ev is not None and ":" in ligne:
            cle, valeur = ligne.split(":", 1)
            nom, *params = cle.split(";")
            try:
                if nom == "DTSTART":
                    ev["debut"] = date(valeur, params)
                elif nom == "DTEND":
                    ev["fin"] = date(valeur, params)
            except ValueError:
                pass
            if nom == "SUMMARY":
                ev["titre"] = propre(valeur)
            elif nom == "LOCATION":
                ev["lieu"] = propre(valeur)
    return sorted(evenements)


def agenda(rafraichir=True):
    """Événements du calendrier (téléchargé au plus toutes les 30 min). Sans connexion, la
    dernière version téléchargée sert. Renvoie [] si rien n'est disponible."""
    a = CFG["infos"]["agenda"]
    lien = a.get("lien", "").strip()
    if not (a.get("actif") and lien):
        return []
    fichier = _cache("agenda.ics")
    try:
        frais = time.time() - os.path.getmtime(fichier) < 1800
    except OSError:
        frais = False
    if rafraichir and not frais:
        url = re.sub(r"^webcal://", "https://", lien, flags=re.I)
        try:
            with urllib.request.urlopen(url, timeout=8) as r:
                donnees = r.read().decode("utf-8", errors="replace")
            if "BEGIN:VCALENDAR" not in donnees:
                raise ValueError("ce lien ne renvoie pas un calendrier .ics")
            with open(fichier, "w", encoding="utf-8") as f:
                f.write(donnees)
        except Exception as e:
            print(f"Emploi du temps indisponible : {e}")
    try:
        with open(fichier, encoding="utf-8") as f:
            return lire_ics(f.read())
    except OSError:
        return []


def cours_du_jour(evenements=None, maintenant=None):
    maintenant = maintenant or datetime.now()
    evenements = agenda() if evenements is None else evenements
    return [e for e in evenements if e[0].date() == maintenant.date() and e[1] > maintenant]


# Mots de passe : Gestionnaire d'identification de Windows (chiffré, lié à ta session), via
# les fonctions CredWrite / CredRead / CredDelete. Jamais dans config.json.
class _CREDENTIAL(ctypes.Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]


def _cible(adresse):
    return f"Runner:{adresse.strip().lower()}"


def enregistrer_mot_de_passe(adresse, mot_de_passe):
    blob = mot_de_passe.encode("utf-16-le")
    tampon = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    cred = _CREDENTIAL(Type=1, TargetName=_cible(adresse), CredentialBlobSize=len(blob),
                       CredentialBlob=tampon, Persist=2, UserName=adresse)   # GENERIC, LOCAL_MACHINE
    if not ctypes.windll.advapi32.CredWriteW(ctypes.byref(cred), 0):
        raise OSError("enregistrement du mot de passe refusé par Windows")


def lire_mot_de_passe(adresse):
    """Mot de passe IMAP gardé dans le Gestionnaire d'identification, ou None."""
    p = ctypes.POINTER(_CREDENTIAL)()
    if not ctypes.windll.advapi32.CredReadW(_cible(adresse), 1, 0, ctypes.byref(p)):
        return None
    try:
        c = p.contents
        return ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize).decode("utf-16-le")
    finally:
        ctypes.windll.advapi32.CredFree(p)


def oublier_mot_de_passe(adresse):
    ctypes.windll.advapi32.CredDeleteW(_cible(adresse), 1, 0)


def _decoder(entete):
    from email.header import decode_header, make_header
    try:
        return str(make_header(decode_header(entete or ""))).strip()
    except Exception:
        return (entete or "").strip()


# « Nouveaux » mails = non lus arrivés depuis le dernier lancement de Runner (7 jours au plus) :
# un total de non lus (souvent des milliers) n'est pas une information utile au réveil.
FICHIER_DERNIER_LANCEMENT = _cache("dernier_lancement")
MAX_NOUVEAUX = 50                                # au-delà : « plus de 50 nouveaux mails »


def depuis_dernier_lancement():
    """Instant (timestamp) à partir duquel un mail non lu compte comme nouveau."""
    try:
        t = os.path.getmtime(FICHIER_DERNIER_LANCEMENT)
    except OSError:
        t = time.time() - 86400                  # premier lancement : les dernières 24 h
    return max(t, time.time() - 7 * 86400)


def noter_lancement():
    with open(FICHIER_DERNIER_LANCEMENT, "w") as f:
        f.write(datetime.now().isoformat(timespec="seconds"))


MOIS_IMAP = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def lire_boite(compte, mot_de_passe=None):
    """{'non_lus': total, 'nouveaux': n, 'derniers': [(expéditeur, objet)…]} pour un compte IMAP.
    Les 'derniers' sont les 5 plus récents des nouveaux. Lecture seule : rien n'est marqué comme lu."""
    import imaplib
    from email.parser import BytesHeaderParser
    from email.utils import parseaddr
    mdp = mot_de_passe or lire_mot_de_passe(compte["adresse"])
    if not mdp:
        raise OSError("mot de passe non enregistré")
    depuis = depuis_dernier_lancement()
    jour = datetime.fromtimestamp(depuis)
    with imaplib.IMAP4_SSL(compte["serveur"].strip(), 993, timeout=10) as imap:
        imap.login(compte["adresse"].strip(), mdp)
        imap.select("INBOX", readonly=True)
        total = len(imap.search(None, "UNSEEN")[1][0].split())
        # SINCE ne connaît que le jour : l'heure exacte d'arrivée est vérifiée ensuite
        ids = imap.search(None, "UNSEEN", "SINCE", f"{jour.day}-{MOIS_IMAP[jour.month - 1]}-{jour.year}")[1][0].split()
        nouveaux = []
        if ids:
            for ligne in imap.fetch(b",".join(ids[-(MAX_NOUVEAUX + 1):]), "(INTERNALDATE)")[1]:
                if isinstance(ligne, bytes):
                    date = imaplib.Internaldate2tuple(ligne)
                    if date and time.mktime(date) > depuis:
                        nouveaux.append(ligne.split()[0])
        derniers = []
        for i in reversed(nouveaux[-5:]):                       # les 5 plus récents
            brut = imap.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")[1][0][1]
            entete = BytesHeaderParser().parsebytes(brut)
            nom, adresse = parseaddr(_decoder(entete.get("From")))
            derniers.append((nom or adresse, _decoder(entete.get("Subject")) or "(sans objet)"))
    return {"non_lus": total, "nouveaux": len(nouveaux), "derniers": derniers}


# Gmail par « Se connecter avec Google » (OAuth 2.0, méthode officielle de Google) : aucun mot de
# passe dans Runner. Autorisation en LECTURE SEULE (gmail.readonly). Le jeton de renouvellement est
# gardé dans le Gestionnaire d'identification de Windows, comme les mots de passe IMAP.
# Il faut un « ID client OAuth » de type « Application de bureau » (fichier google_client.json).
FICHIER_GOOGLE = os.path.join(DOSSIER, "google_client.json")
PORTEE_GMAIL = "https://www.googleapis.com/auth/gmail.readonly"
API_GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
_jetons = {}                                     # adresse -> (jeton d'accès, expiration)

_PAGE_CONNEXION = """<!DOCTYPE html><html lang="fr"><meta charset="utf-8"><title>Runner</title>
<body style="background:#1f1e1d;color:#ecebe6;font:18px 'Segoe UI',sans-serif;display:flex;
align-items:center;justify-content:center;height:90vh"><div style="text-align:center">
<p style="font-size:26px">{titre}</p><p style="color:#9c9a92">{texte}</p></div></body></html>"""


def client_google():
    """(client_id, client_secret) du fichier téléchargé depuis Google Cloud."""
    with open(FICHIER_GOOGLE, encoding="utf-8") as f:
        d = json.load(f)
    d = d.get("installed") or d.get("web") or d
    return d["client_id"], d.get("client_secret", "")


def _api(url, donnees=None, jeton=None):
    """Requête HTTPS vers Google ; renvoie le JSON, ou lève OSError avec le message de Google."""
    import urllib.error
    req = urllib.request.Request(url, data=urllib.parse.urlencode(donnees).encode() if donnees else None)
    if jeton:
        req.add_header("Authorization", f"Bearer {jeton}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e)
            detail = detail.get("error_description") or detail.get("error", {})
            detail = detail.get("message", detail) if isinstance(detail, dict) else detail
        except Exception:
            detail = e.reason
        raise OSError(f"{e.code} {detail}") from None


def connecter_google(attente=300):
    """Ouvre la page de connexion Google dans le navigateur, attend l'autorisation et garde le
    jeton dans Windows. Renvoie l'adresse Gmail connectée.
    Flux « application de bureau » : redirection vers 127.0.0.1 + PKCE (recommandé par Google)."""
    import hashlib
    import http.server
    import secrets
    import webbrowser
    client_id, secret = client_google()
    verif = secrets.token_urlsafe(64)
    defi = base64.urlsafe_b64encode(hashlib.sha256(verif.encode()).digest()).rstrip(b"=").decode()
    etat, res = secrets.token_urlsafe(16), {}

    class Reponse(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == etat:
                res.update({k: v[0] for k, v in q.items()})
            ok = "code" in res
            page = _PAGE_CONNEXION.format(
                titre="Runner est connecté à Gmail ✓" if ok else "Connexion annulée",
                texte="Tu peux fermer cet onglet." if ok else "Tu peux fermer cet onglet et réessayer depuis Runner.")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode())

        def log_message(self, *_):
            pass

    serveur = http.server.HTTPServer(("127.0.0.1", 0), Reponse)
    serveur.timeout = 1
    redirection = f"http://127.0.0.1:{serveur.server_port}"
    webbrowser.open("https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirection, "response_type": "code",
        "scope": PORTEE_GMAIL, "code_challenge": defi, "code_challenge_method": "S256",
        "state": etat, "access_type": "offline", "prompt": "consent"}))
    fin = time.time() + attente
    try:
        while "code" not in res and "error" not in res and time.time() < fin:
            serveur.handle_request()
    finally:
        serveur.server_close()
    if "error" in res:
        raise OSError(f"autorisation refusée ({res['error']})")
    if "code" not in res:
        raise OSError("pas de réponse de Google (délai dépassé)")
    jetons = _api("https://oauth2.googleapis.com/token", {
        "code": res["code"], "client_id": client_id, "client_secret": secret, "code_verifier": verif,
        "grant_type": "authorization_code", "redirect_uri": redirection})
    if "refresh_token" not in jetons:
        raise OSError("Google n'a pas fourni de jeton de renouvellement")
    adresse = _api(f"{API_GMAIL}/profile", jeton=jetons["access_token"])["emailAddress"]
    enregistrer_mot_de_passe(f"google:{adresse}", jetons["refresh_token"])
    _jetons[adresse] = (jetons["access_token"], time.time() + int(jetons.get("expires_in", 3600)) - 60)
    print(f"Gmail connecté : {adresse}")
    return adresse


def deconnecter_google(adresse):
    """Révoque l'autorisation chez Google et oublie le jeton."""
    jeton = lire_mot_de_passe(f"google:{adresse}")
    if jeton:
        try:
            _api("https://oauth2.googleapis.com/revoke", {"token": jeton})
        except OSError:
            pass
    oublier_mot_de_passe(f"google:{adresse}")
    _jetons.pop(adresse, None)


def jeton_google(adresse):
    """Jeton d'accès valide (renouvelé tout seul, valable environ 1 h)."""
    jeton, expiration = _jetons.get(adresse, (None, 0))
    if jeton and time.time() < expiration:
        return jeton
    renouvellement = lire_mot_de_passe(f"google:{adresse}")
    if not renouvellement:
        raise OSError("compte Google non connecté (page Infos)")
    client_id, secret = client_google()
    try:
        r = _api("https://oauth2.googleapis.com/token", {
            "client_id": client_id, "client_secret": secret, "refresh_token": renouvellement,
            "grant_type": "refresh_token"})
    except OSError as e:
        if "invalid_grant" in str(e) or "expired" in str(e).lower():
            raise OSError("connexion Google expirée ou révoquée : reconnecte-toi (page Infos)") from None
        raise
    _jetons[adresse] = (r["access_token"], time.time() + int(r.get("expires_in", 3600)) - 60)
    return r["access_token"]


def lire_gmail(compte):
    """Même résultat que lire_boite, par l'API Gmail en lecture seule."""
    jeton = jeton_google(compte["adresse"])
    non_lus = _api(f"{API_GMAIL}/labels/INBOX", jeton=jeton).get("messagesUnread", 0)
    requete = f"is:unread in:inbox after:{int(depuis_dernier_lancement())}"
    nouveaux = _api(f"{API_GMAIL}/messages?" + urllib.parse.urlencode({"q": requete, "maxResults": MAX_NOUVEAUX + 1}),
                    jeton=jeton).get("messages", [])
    liste = nouveaux[:5]
    from email.utils import parseaddr
    derniers = []
    for m in liste:
        d = _api(f"{API_GMAIL}/messages/{m['id']}?format=metadata&metadataHeaders=From&metadataHeaders=Subject",
                 jeton=jeton)
        entetes = {h["name"].lower(): h["value"] for h in d.get("payload", {}).get("headers", [])}
        nom, adresse = parseaddr(entetes.get("from", ""))
        derniers.append((nom or adresse, entetes.get("subject") or "(sans objet)"))
    return {"non_lus": non_lus, "nouveaux": len(nouveaux), "derniers": derniers}


_mails = {"t": 0, "val": None}


def etat_mails(rafraichir=True):
    """{nom du compte: résultat de lire_boite ou message d'erreur} ; relu au plus toutes les 5 min."""
    m = CFG["infos"]["mails"]
    comptes = [c for c in m.get("comptes", []) if c.get("actif", True) and c.get("adresse")
               and (c.get("type") == "gmail" or c.get("serveur"))]
    if not (m.get("actif") and comptes):
        return {}
    if rafraichir and time.time() - _mails["t"] > 300:
        res = {}
        for c in comptes:
            try:
                res[c.get("nom") or c["adresse"]] = lire_gmail(c) if c.get("type") == "gmail" else lire_boite(c)
            except Exception as e:
                res[c.get("nom") or c["adresse"]] = f"{e}"
                print(f"Mails « {c.get('nom') or c['adresse']} » indisponibles : {e}")
        _mails.update(t=time.time(), val=res)
    return _mails["val"] or {}


def phrase_mails(etat):
    """« Vous avez 3 nouveaux mails, dont le dernier de Marie Dupont » (ou None si rien à dire).
    Nouveaux = non lus arrivés depuis le dernier lancement de Runner."""
    boites = [b for b in etat.values() if isinstance(b, dict)]
    if not boites:
        return None
    n = sum(b.get("nouveaux", 0) for b in boites)
    if n == 0:
        return "Aucun nouveau mail"
    if n > MAX_NOUVEAUX:
        return f"Vous avez plus de {MAX_NOUVEAUX} nouveaux mails"
    phrase = f"Vous avez {n} nouveau{'x' if n > 1 else ''} mail{'s' if n > 1 else ''}"
    dernier = next((b["derniers"][0][0] for b in boites if b["derniers"]), "")
    if dernier:
        phrase += f", dont le dernier de {dernier}" if n > 1 else f", de {dernier}"
    return phrase


def ouvrir_recap():
    """Petite fenêtre au thème de Runner : cours du jour et mails non lus (processus à part)."""
    i = CFG["infos"]
    donnees = {"cours": [(d.isoformat(), f.isoformat(), t, l) for d, f, t, l in cours_du_jour()],
               "agenda": bool(i["agenda"].get("actif") and i["agenda"].get("lien")),
               "mails": etat_mails(), "webmails": {c.get("nom") or c["adresse"]: c.get("webmail", "")
                                                    for c in i["mails"].get("comptes", [])}}
    if not (donnees["agenda"] or donnees["mails"]):
        return
    fichier = _cache("recap.json")
    ecrire_json(fichier, donnees, sauvegarde=False)
    subprocess.Popen([lanceur_python(), os.path.join(DOSSIER, "clap_config.py"), "--recap", fichier],
                     cwd=DOSSIER, creationflags=DETACHE)


PARTIES = ["accueil", "heure", "meteo", "cours", "mails", "fin"]


def texte_phrase(m=False, apercu=False, rafraichir=True):
    """Assemble les parties actives. Variables : {heure} ; {temperature} {ciel} {ville} ;
    {cours} {heure_cours} {salle} ; {nb_mails} {expediteur} {objet} (et {mails}, la phrase
    toute faite). Pour les mails, le modèle dépend du nombre de nouveaux mails (plusieurs, un, aucun).
    Une partie dont l'information manque
    (pas de météo, plus de cours aujourd'hui, mails non configurés) est sautée.
    'm' : météo imposée ; 'apercu' : sans connexion, avec des exemples si besoin ;
    'rafraichir' False : agenda et mails déjà en mémoire (au lancement, pour ne pas attendre)."""
    v, now = CFG["voix"], datetime.now()
    m = meteo() if m is False else m
    infos = {"heure": dire_heure(now), "ville": v["ville"]}
    if m:
        infos["temperature"] = f"moins {-m[0]}" if m[0] < 0 else str(m[0])
        infos["ciel"] = METEO.get(m[1] if m[1] < 4 else m[1] // 10 * 10, "un ciel changeant")
    cours = cours_du_jour(agenda(rafraichir=not apercu and (rafraichir or not os.path.exists(_cache("agenda.ics")))))
    if apercu and not cours:
        exemple = now.replace(minute=0, second=0) + timedelta(hours=1)
        cours = [(exemple, exemple, "Thermodynamique", "Amphi B")]
    cours = [c for c in cours if (c[0] - now).total_seconds() > -300]     # pas encore commencé
    if cours:
        debut, _, titre, lieu = cours[0]
        infos.update(cours=titre, heure_cours=dire_heure(debut), salle=f", en {lieu}" if lieu else "")
    boites = etat_mails(rafraichir=not apercu and (rafraichir or _mails["val"] is None))
    mails = phrase_mails(boites)
    nb = sum(b.get("nouveaux", 0) for b in boites.values() if isinstance(b, dict))
    dernier = next((b["derniers"][0] for b in boites.values() if isinstance(b, dict) and b["derniers"]), ("", ""))
    if apercu and mails is None:
        mails, nb, dernier = "Vous avez 3 nouveaux mails, dont le dernier de la scolarité", 3, ("la scolarité", "Réunion")
    if mails:
        infos.update(mails=mails, nb=nb, expediteur=dernier[0] or "quelqu'un", objet=dernier[1],
                     nb_mails=f"plus de {MAX_NOUVEAUX}" if nb > MAX_NOUVEAUX else str(nb))
    besoin = {"meteo": "temperature", "cours": "cours", "mails": "mails"}
    morceaux = []
    for nom in PARTIES:
        p = v["parties"].get(nom, {})
        texte = p.get("texte", "")
        if nom == "mails" and "nb" in infos:      # phrase selon le nombre de nouveaux mails
            texte = {0: p.get("aucun", ""), 1: p.get("un") or texte}.get(infos["nb"], texte)
        if p.get("actif") and texte.strip() and besoin.get(nom, "heure") in infos:
            morceaux.append(texte.strip().format_map(
                type("D", (dict,), {"__missing__": lambda s, k: ""})(infos)))
    return " ".join(morceaux)


# La phrase est préparée à l'avance (et refaite à chaque minute) pendant l'écoute, et
# aussi par la fenêtre de réglage quand elle est ouverte. Le fichier est partagé sur le
# disque : au double clap comme au test, elle est lue instantanément.
_audio = {"fichier": os.path.join(tempfile.gettempdir(), "runner.wav")}
_audio["cle"] = _audio["fichier"] + ".cle"


def synthetiser(texte, voix, fichier):
    """Synthèse edge-tts (MP3), convertie une fois pour toutes en WAV : la lecture est ensuite
    instantanée et le décodeur MP3 ne s'exécute plus pendant que Runner parle."""
    import asyncio
    import edge_tts
    import soundfile as sf
    unique = f"{fichier}.{os.getpid()}.{threading.get_ident()}"   # pas de conflit entre processus
    mp3, wav = unique + ".tmp.mp3", unique + ".tmp.wav"
    try:
        asyncio.run(edge_tts.Communicate(texte, voix).save(mp3))
        donnees, taux = sf.read(mp3, dtype="float32")
        sf.write(wav, donnees, taux)
        for essai in range(10):                  # le fichier peut être lu un instant ailleurs
            try:
                os.replace(wav, fichier)
                break
            except PermissionError:
                if essai == 9:
                    raise
                time.sleep(0.2)
    finally:
        for f in (mp3, wav):
            try:
                os.remove(f)
            except OSError:
                pass


def _deja_pret(fichier_cle, cle):
    """Chemin du fichier audio déjà préparé pour cette clé, ou None."""
    try:
        with open(fichier_cle, encoding="utf-8") as f:
            d = json.load(f)
        if d["cle"] == cle and os.path.exists(d["fichier"]):
            return d["fichier"]
    except (FileNotFoundError, ValueError, KeyError):
        pass
    return None


def _noter_pret(fichier_cle, cle, fichier):
    try:
        ecrire_json(fichier_cle, {"cle": cle, "fichier": fichier}, sauvegarde=False)
    except OSError:
        pass


class _Verrou:
    """Verrou entre processus (fichier créé en exclusivité) : la fenêtre de réglages et Runner
    ne préparent pas la même phrase en même temps. Un verrou de plus de 60 s est périmé."""

    def __init__(self, nom, attente=20):
        self.chemin, self.attente, self.pris = nom + ".verrou", attente, False

    def __enter__(self):
        fin = time.time() + self.attente
        while time.time() < fin:
            try:
                os.close(os.open(self.chemin, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                self.pris = True
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.chemin) > 60:
                        os.remove(self.chemin)
                        continue
                except OSError:
                    pass
                time.sleep(0.2)
        return self                              # on continue quand même au bout du délai

    def __exit__(self, *_):
        if self.pris:
            try:
                os.remove(self.chemin)
            except OSError:
                pass


def preparer_voix(rafraichir=True):
    """Synthétise la phrase du moment si le fichier sur le disque n'est pas déjà la bonne."""
    texte = texte_phrase(rafraichir=rafraichir)
    cle = json.dumps([texte, CFG["voix"]["voix"]], ensure_ascii=False)
    if not _deja_pret(_audio["cle"], cle):
        with _Verrou(_audio["fichier"]):
            if not _deja_pret(_audio["cle"], cle):   # peut-être préparée entre-temps par un autre
                synthetiser(texte, CFG["voix"]["voix"], _audio["fichier"])
                _noter_pret(_audio["cle"], cle, _audio["fichier"])
    return texte


# Phrase de secours : sans heure ni météo, préparée une fois pour toutes. Utilisée si la
# phrase principale n'est pas prête à temps. Sans Internet, voix intégrée de Windows.
_secours = {"cle": os.path.join(tempfile.gettempdir(), "runner_secours.cle"),
            "neurale": os.path.join(tempfile.gettempdir(), "runner_secours_neurale.wav"),
            "wav": os.path.join(tempfile.gettempdir(), "runner_secours.wav")}


def texte_secours():
    return CFG["voix"]["secours"].strip() or "Votre espace de travail est prêt."


def preparer_secours():
    with _Verrou(_secours["cle"]):
        return _preparer_secours()


def _preparer_secours():
    """Synthétise la phrase de secours si elle a changé (voix neurale si possible)."""
    texte = texte_secours()
    cle = json.dumps([texte, CFG["voix"]["voix"]], ensure_ascii=False)
    deja = _deja_pret(_secours["cle"], cle)
    if deja == _secours["neurale"]:
        return deja
    try:
        synthetiser(texte, CFG["voix"]["voix"], _secours["neurale"])
        fichier = _secours["neurale"]
    except Exception:
        if deja:                                 # déjà une version Windows : on la garde
            return deja
        powershell("Add-Type -AssemblyName System.Speech;"
                   "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                   f"$s.SetOutputToWaveFile({ps_texte(_secours['wav'])});"
                   f"$s.Speak({ps_texte(texte)});$s.Dispose()")
        fichier = _secours["wav"]
    _noter_pret(_secours["cle"], cle, fichier)
    return fichier


def voix_de_secours():
    """Fichier de la phrase de secours (préparé si besoin), ou None."""
    cle = json.dumps([texte_secours(), CFG["voix"]["voix"]], ensure_ascii=False)
    try:
        return _deja_pret(_secours["cle"], cle) or preparer_secours()
    except Exception as e:
        print(f"Phrase de secours indisponible : {e}")
        return None


def preparer_voix_en_boucle():
    while True:
        try:
            preparer_secours()                   # instantané une fois faite
            preparer_voix()
        except Exception as e:
            print(f"Préparation de la voix impossible : {e}")
        time.sleep(61 - datetime.now().second)       # juste après chaque changement de minute


def parler(fichier=None):
    """Dit la phrase de Runner (la principale par défaut) en baissant la musique."""
    if not CFG["voix"]["active"]:
        return
    try:
        if fichier is None:
            print(f"Runner : {preparer_voix(rafraichir=False)}")
            fichier = _audio["fichier"]
        mu, musique = CFG["musique"], _musique["lecteur"]
        if musique and mu["pendant_voix_pct"] < 100:
            musique.regler(mu["volume_pct"] / 100 * mu["pendant_voix_pct"] / 100)
            time.sleep(0.25)                     # la musique commence à baisser juste avant la voix
        Lecteur(fichier).jouer().attendre(arret_demande)
    except Exception as e:
        print(f"Voix indisponible : {e}")
    finally:
        if _musique["lecteur"]:
            _musique["lecteur"].regler(CFG["musique"]["volume_pct"] / 100)


# ------------------------ Point d'accès & démarrage ------------------------
# Script PowerShell (API Windows « NetworkOperatorTetheringManager ») : active le point
# d'accès mobile en partageant la connexion Internet actuelle (eduroam).
_PS_POINT_ACCES = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? { $_.Name -eq 'AsTask' -and
  $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
$p = [Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]::GetInternetConnectionProfile()
if (-not $p) { 'PAS_INTERNET'; exit 2 }
$m = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]::CreateFromConnectionProfile($p)
if ($m.TetheringOperationalState -eq 1) { 'DEJA_ACTIF'; exit 0 }
$t = $asTask.MakeGenericMethod([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult]).Invoke($null, @($m.StartTetheringAsync()))
$t.Wait(-1) | Out-Null
if ($t.Result.Status -eq 0) { 'ACTIVE'; exit 0 } else { 'ECHEC ' + $t.Result.Status + ' ' + $t.Result.AdditionalErrorMessage; exit 1 }
"""


def point_acces_actif():
    """Le point d'accès de Windows donne au PC l'adresse 192.168.137.1 : vérification
    instantanée, sans lancer PowerShell."""
    try:
        return "192.168.137.1" in {i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        return False


def internet_disponible():
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=2).close()
        return True
    except OSError:
        return False


def activer_point_acces(attente_max=0):
    """Active le point d'accès Wi-Fi. Réessaie jusqu'à 'attente_max' s (ex. : à l'allumage
    du PC, le temps qu'eduroam se connecte). Renvoie (ok, message).
    PowerShell n'est lancé que si c'est utile : point d'accès inactif et Internet disponible."""
    fin = time.time() + attente_max
    while True:
        if point_acces_actif():
            print("Point d'accès : DEJA_ACTIF")
            return True, "DEJA_ACTIF"
        if not internet_disponible():
            if time.time() >= fin:
                print("Point d'accès : PAS_INTERNET")
                return False, "PAS_INTERNET"
            time.sleep(5)
            continue
        try:
            r = powershell(_PS_POINT_ACCES, timeout=40)
            message = (r.stdout.strip().splitlines() or [r.stderr.strip() or "?"])[-1]
            ok = r.returncode == 0
        except Exception as e:
            ok, message = False, str(e)
        if ok or time.time() >= fin:
            print(f"Point d'accès : {message}")
            return ok, message
        time.sleep(10)


DOSSIER_DEMARRAGE = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
RACCOURCI_DEMARRAGE = os.path.join(DOSSIER_DEMARRAGE, "Runner.lnk")


RACCOURCI_BUREAU = "Runner.lnk"            # ouvre la fenêtre de réglages
ICONE = os.path.join(DOSSIER, "runner.ico")              # logo de Runner (raccourcis et fenêtres)


def lanceur_python():
    """Programme utilisé par les raccourcis. De préférence pyw.exe, le lanceur Python de Windows,
    qui prend toujours la version installée la plus récente : les raccourcis survivent ainsi
    aux mises à jour de Python. À défaut, le pythonw.exe actuel."""
    for c in (os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "pyw.exe"),
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Launcher\pyw.exe"),
              shutil.which("pyw") or ""):
        if c and os.path.exists(c):
            return c
    return os.path.join(os.path.dirname(sys.executable), "pythonw.exe")


FICHIER_RACCOURCIS = os.path.join(tempfile.gettempdir(), "runner_raccourcis.json")


def dossier_bureau():
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
        return os.path.expandvars(winreg.QueryValueEx(k, "Desktop")[0])


def raccourcis_a_jour(bureau):
    """True si rien n'a changé depuis la dernière vérification réussie : même lanceur Python
    (toujours présent), même dossier, raccourcis présents et non modifiés. Évite PowerShell."""
    try:
        with open(FICHIER_RACCOURCIS, encoding="utf-8") as f:
            avant = json.load(f)
        maintenant = etat_raccourcis()
        if bureau and maintenant["bureau"] is None:      # raccourci du Bureau supprimé : à refaire
            return False
        return avant == maintenant and os.path.exists(avant["lanceur"])
    except (OSError, ValueError, KeyError):
        return False


def etat_raccourcis():
    """État des raccourcis (lanceur Python, dossier, date des raccourcis Démarrage et Bureau, logo) :
    sert à savoir s'ils doivent être refaits."""
    def date(p):
        return os.path.getmtime(p) if os.path.exists(p) else None
    try:
        lnk_bureau = os.path.join(dossier_bureau(), RACCOURCI_BUREAU)
    except OSError:
        lnk_bureau = ""
    return {"lanceur": lanceur_python(), "dossier": DOSSIER, "demarrage": date(RACCOURCI_DEMARRAGE),
            "bureau": date(lnk_bureau) if lnk_bureau else None, "icone": os.path.exists(ICONE)}


def reparer_raccourcis(demarrage=None, bureau=False):
    """Vérifie les raccourcis de Runner et refait ceux qui sont cassés ou périmés (Python
    déplacé ou mis à jour…). demarrage : True = créer, False = retirer, None = réparer s'il
    existe. bureau : True = créer le raccourci du Bureau s'il manque."""
    if demarrage is False and os.path.exists(RACCOURCI_DEMARRAGE):
        os.remove(RACCOURCI_DEMARRAGE)
    if demarrage is None and raccourcis_a_jour(bureau):
        return
    lanceur = lanceur_python()
    raccourcis = [("Startup", "Runner.lnk", "clap_launcher.py", demarrage is True)] if demarrage is not False else []
    raccourcis.append(("Desktop", RACCOURCI_BUREAU, "clap_config.py", bureau))
    ps = ["$w = New-Object -ComObject WScript.Shell"]
    for dossier, nom, script, creer in raccourcis:
        script, cible = os.path.join(DOSSIER, script), ps_texte(lanceur)
        icone = ps_texte(ICONE + ",0" if os.path.exists(ICONE) else "")
        ps.append(
            f"$l = Join-Path ([Environment]::GetFolderPath('{dossier}')) {ps_texte(nom)};"
            f"if ((Test-Path -LiteralPath $l) -or ${str(creer).lower()}) {{"
            f"  $s = $w.CreateShortcut($l); $a = {ps_texte(chr(34) + script + chr(34))};"
            f"  if ($s.TargetPath -ne {cible} -or $s.Arguments -ne $a -or ({icone} -and $s.IconLocation -ne {icone})"
            f"      -or -not (Test-Path -LiteralPath $s.TargetPath)) {{"
            f"    $s.TargetPath = {cible}; $s.Arguments = $a; $s.WorkingDirectory = {ps_texte(DOSSIER)};"
            f"    if ({icone}) {{ $s.IconLocation = {icone} }};"
            f"    $s.Save(); 'REPARE:{dossier}' }} }}")
    try:
        r = powershell("\n".join(ps))
        for ligne in r.stdout.splitlines():           # (sortie sans accents : encodage de la console)
            if ligne.startswith("REPARE:"):
                ou = "du Bureau" if "Desktop" in ligne else "du Démarrage"
                print(f"Raccourci {ou} réparé ou créé")
        with open(FICHIER_RACCOURCIS, "w", encoding="utf-8") as f:
            json.dump(etat_raccourcis(), f)
    except Exception as e:
        print(f"Vérification des raccourcis impossible : {e}")


TACHE_REVEIL = "Runner\\Reveil"
_EVENEMENTS_REVEIL = ("*[System[(Provider[@Name='Microsoft-Windows-Power-Troubleshooter'] and EventID=1)"
                      " or (Provider[@Name='Microsoft-Windows-Kernel-Power'] and EventID=507)]]")


def reveil_actif():
    r = subprocess.run(["schtasks", "/query", "/tn", TACHE_REVEIL], capture_output=True,
                       creationflags=SANS_FENETRE)
    return r.returncode == 0


def regler_reveil(actif):
    """Tâche planifiée Windows qui lance Runner à la sortie de veille (veille classique : événement
    Power-Troubleshooter 1 ; veille moderne des portables : Kernel-Power 507)."""
    if actif:
        cible = f'"{lanceur_python()}" "{os.path.join(DOSSIER, "clap_launcher.py")}"'
        r = subprocess.run(["schtasks", "/create", "/f", "/tn", TACHE_REVEIL, "/sc", "onevent",
                            "/ec", "System", "/mo", _EVENEMENTS_REVEIL, "/tr", cible, "/rl", "limited"],
                           capture_output=True, text=True, creationflags=SANS_FENETRE)
    else:
        if not reveil_actif():
            return
        r = subprocess.run(["schtasks", "/delete", "/f", "/tn", TACHE_REVEIL],
                           capture_output=True, text=True, creationflags=SANS_FENETRE)
    if r.returncode != 0:
        raise OSError((r.stderr or r.stdout).strip() or "schtasks a échoué")
    print("Lancement à la sortie de veille " + ("activé" if actif else "désactivé"))


def regler_demarrage_session(actif):
    """Ajoute ou retire Runner du dossier Démarrage de Windows."""
    reparer_raccourcis(demarrage=bool(actif))


def migrer_ancien_nom():
    """L'assistant s'appelait Jarvis, et le raccourci du Bureau « Runner - réglages » : journal et
    raccourcis sont renommés (instantané,
    sans PowerShell ; les raccourcis pointent toujours vers les mêmes scripts)."""
    renommages = [("jarvis.log", FICHIER_LOG), ("jarvis.ancien.log", os.path.join(DOSSIER, "runner.ancien.log")),
                  (os.path.join(DOSSIER_DEMARRAGE, "Jarvis.lnk"), RACCOURCI_DEMARRAGE)]
    try:
        bureau = dossier_bureau()
        for ancien in ("Jarvis - réglages.lnk", "Runner - réglages.lnk"):
            renommages.append((os.path.join(bureau, ancien), os.path.join(bureau, RACCOURCI_BUREAU)))
    except OSError:
        pass
    for ancien, nouveau in renommages:
        ancien = os.path.join(DOSSIER, ancien)          # (sans effet sur un chemin absolu)
        if not os.path.exists(ancien):
            continue
        try:
            if not os.path.exists(nouveau):
                os.replace(ancien, nouveau)
            elif ancien.endswith(".lnk"):
                os.remove(ancien)                       # doublon de raccourci
        except OSError:
            pass


def migrer_tache_reveil():
    """Remplace l'ancienne tâche de sortie de veille « Jarvis\\Reveil » (vérifié une seule fois)."""
    fait = os.path.join(tempfile.gettempdir(), "runner_migration_tache")
    if os.path.exists(fait):
        return
    try:
        ancienne = subprocess.run(["schtasks", "/query", "/tn", "Jarvis\\Reveil"], capture_output=True,
                                  creationflags=SANS_FENETRE).returncode == 0
        if ancienne:
            subprocess.run(["schtasks", "/delete", "/f", "/tn", "Jarvis\\Reveil"], capture_output=True,
                           creationflags=SANS_FENETRE)
            regler_reveil(True)
        open(fait, "w").close()
    except Exception as e:
        print(f"Reprise de l'ancienne tâche de sortie de veille impossible : {e}")


# -------------------------- Fenêtres (Windows) ---------------------------
user32, dwmapi = ctypes.windll.user32, ctypes.windll.dwmapi
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))   # vrais pixels, même avec zoom
except Exception:
    pass


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


MonitorProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                 ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
WindowProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.GetWindow.restype = wintypes.HWND
kernel32.OpenProcess.restype = wintypes.HANDLE


def zone_ecran(nom):
    """Zone utile (sans barre des tâches) de l'écran 'principal' ou 'secondaire'."""
    ecrans = []

    def cb(h, *_):
        mi = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        user32.GetMonitorInfoW(h, ctypes.byref(mi))
        r = mi.rcWork
        ecrans.append((bool(mi.dwFlags & 1), (r.left, r.top, r.right, r.bottom)))
        return True

    user32.EnumDisplayMonitors(None, None, MonitorProc(cb), 0)
    voulu = nom == "principal"
    return next((z for p, z in ecrans if p == voulu), ecrans[0][1])


def fenetres():
    """{hwnd: exe} des fenêtres principales visibles."""
    res = {}

    def cb(h, _):
        if user32.IsWindowVisible(h) and not user32.GetWindow(h, 4) and user32.GetWindowTextLengthW(h):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            hp = kernel32.OpenProcess(0x1000, False, pid.value)
            if hp:
                buf, n = ctypes.create_unicode_buffer(512), wintypes.DWORD(512)
                if kernel32.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(n)):
                    res[h] = os.path.basename(buf.value).lower()
                kernel32.CloseHandle(hp)
        return True

    user32.EnumWindows(WindowProc(cb), 0)
    return res


def placer(h, app):
    """Place la fenêtre 'h' dans sa zone d'écran (en compensant les bordures invisibles de Windows)."""
    g, t, d, b = zone_ecran(app["ecran"])
    f0, f1 = ZONES[app["zone"]]
    l, r = g + round((d - g) * f0), g + round((d - g) * f1)
    user32.ShowWindow(h, 9)                                   # SW_RESTORE
    wr, fr = wintypes.RECT(), wintypes.RECT()                 # compense les bordures invisibles
    user32.GetWindowRect(h, ctypes.byref(wr))
    if dwmapi.DwmGetWindowAttribute(h, 9, ctypes.byref(fr), ctypes.sizeof(fr)) == 0:
        l, t = l - (fr.left - wr.left), t - (fr.top - wr.top)
        r, b = r + (wr.right - fr.right), b + (wr.bottom - fr.bottom)
    user32.SetWindowPos(h, None, l, t, r - l, b - t, 0x0044)  # NOZORDER | SHOWWINDOW
    if app["zone"] == "plein":
        user32.ShowWindow(h, 3)                               # SW_MAXIMIZE


# ------------------------------- Lancement -------------------------------
def decouper_args(texte):
    """Découpe les arguments ; un chemin existant (même avec espaces) reste en un seul morceau."""
    texte = texte.strip()
    if not texte:
        return []
    seul = os.path.expandvars(texte.strip('"'))
    if os.path.exists(seul) or seul.lower().endswith(".exe"):
        return [seul]
    return [a.strip('"') for a in shlex.split(texte, posix=False)]


FICHIER_FENETRES = os.path.join(tempfile.gettempdir(), "runner_fenetres.json")

_PS_ONGLETS = r"""
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$f = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]HWND)
$c = New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
  [System.Windows.Automation.ControlType]::TabItem)
$f.FindAll([System.Windows.Automation.TreeScope]::Descendants, $c) | % { $_.Current.Name }
"""


def titres_onglets(hwnd):
    """Titres des onglets d'une fenêtre de navigateur (via l'accessibilité de Windows), ou None."""
    script = _PS_ONGLETS.replace("HWND", str(int(hwnd)))
    try:
        r = powershell(script, timeout=12)
        titres = [t.strip() for t in r.stdout.splitlines() if t.strip()]
        return titres if r.returncode == 0 and titres else None
    except Exception:
        return None


def deja_dans_un_onglet(url, titres):
    """Un onglet correspond si son titre contient un mot de l'adresse (youtube, github, moodle…)."""
    hote = urllib.parse.urlparse(url if "://" in url else "https://" + url).netloc.lower().split(":")[0]
    if not hote:
        return False
    mots = [m for m in hote.split(".")[:-1] if m != "www" and len(m) >= 4] or hote.split(".")[:1]
    return any(m in t.lower() for t in titres for m in mots)


def fenetre_navigateur(nom, actuelles):
    """Fenêtre du navigateur à réutiliser : celle ouverte par Runner la dernière fois si elle
    existe encore, sinon la plus récemment utilisée."""
    try:
        with open(FICHIER_FENETRES, encoding="utf-8") as f:
            h = json.load(f).get(nom)
        if h and actuelles.get(h) == nom:
            return h
    except (FileNotFoundError, ValueError):
        pass
    return next((h for h, exe in actuelles.items() if exe == nom), None)


def retenir_fenetre(nom, hwnd):
    """Mémorise la fenêtre ouverte pour cette appli : au lancement suivant, elle est réutilisée."""
    try:
        with open(FICHIER_FENETRES, encoding="utf-8") as f:
            d = json.load(f)
    except (FileNotFoundError, ValueError):
        d = {}
    d[nom] = int(hwnd)
    with open(FICHIER_FENETRES, "w", encoding="utf-8") as f:
        json.dump(d, f)


def premier_plan(hwnd):
    user32.keybd_event(0x12, 0, 0, 0)            # appui bref sur Alt : Windows autorise alors
    user32.keybd_event(0x12, 0, 2, 0)            # le changement de fenêtre au premier plan
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)


def lancer_app(app, actuelles=None):
    """Lance une app détachée du terminal. Renvoie (nom du .exe, fenêtre existante à placer ou
    None, déjà ouverte ?) ; nom None si introuvable.
    - App déjà ouverte : pas relancée, sa fenêtre sera replacée.
    - Navigateur déjà ouvert : pas de nouvelle fenêtre ; seuls les onglets absents sont ajoutés."""
    actuelles = actuelles or {}
    args = decouper_args(app.get("args", ""))
    if not app.get("exe") and args and args[0].lower().endswith(".exe"):
        app = dict(app, exe=args.pop(0))          # chemin du .exe donné comme argument
    exe = chemin(app.get("exe", ""))
    if not exe:
        print(f"Introuvable : {app.get('exe')}")
        return None, None, False
    nom = os.path.basename(exe).lower()
    navigateur = nom in NAVIGATEURS
    lancer = lambda a: subprocess.Popen([exe] + a, creationflags=DETACHE, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        close_fds=True)
    if nom in actuelles.values():
        if not navigateur:
            print(f"Déjà ouverte : {nom}")
            return nom, None, True
        hwnd = fenetre_navigateur(nom, actuelles)
        urls = [a for a in args if not a.startswith("-")]
        titres = titres_onglets(hwnd) if urls else []
        manquants = urls if titres is None else [u for u in urls if not deja_dans_un_onglet(u, titres)]
        print(f"{nom} déjà ouvert : onglets ajoutés {manquants or 'aucun'}")
        if manquants:
            premier_plan(hwnd)                    # les nouveaux onglets vont dans cette fenêtre
            time.sleep(0.3)
            lancer(manquants)
        return nom, hwnd, True
    lancer((["--new-window"] if navigateur else []) + args)
    return nom, None, False


def apps_du_lancement():
    """Les apps des réglages ; avec « ouvrir le webmail », ses onglets sont ajoutés au premier
    navigateur de la liste."""
    apps = [dict(a) for a in CFG["apps"]]
    i = CFG["infos"]
    webmails = [c["webmail"] for c in i["mails"].get("comptes", [])
                if i["mails"].get("actif") and c.get("actif", True) and c.get("webmail")]
    if i.get("ouvrir_webmail") and webmails:
        nav = next((a for a in apps if os.path.basename(chemin(a.get("exe", "")) or "").lower() in NAVIGATEURS), None)
        if nav:
            nav["args"] = " ".join([nav.get("args", "")] + webmails).strip()
        else:
            print("Webmail : aucun navigateur dans les apps, onglet non ouvert")
    return apps


def lancer_et_placer_apps():
    """Lance les apps (sauf celles déjà ouvertes) et place leurs fenêtres."""
    avant = fenetres()
    deja_la = set(avant)
    restantes, trouvees = [], {}
    def est_navigateur(app):
        exe = chemin(app.get("exe", "")) or ""
        return os.path.basename(exe).lower() in NAVIGATEURS
    for app in sorted(apps_du_lancement(), key=est_navigateur):     # navigateurs en dernier
        nom, hwnd, existante = lancer_app(app, avant)
        if hwnd:
            trouvees[hwnd] = dict(app, processus=nom)
        elif nom:
            restantes.append(dict(app, processus=nom, existante=existante))

    # Attente des fenêtres (max 25 s ; après 8 s on accepte une fenêtre déjà ouverte,
    # sauf pour les navigateurs : on ne déplace jamais tes autres fenêtres)
    debut = time.time()
    while restantes and time.time() - debut < 25:
        time.sleep(0.4)
        actuelles = fenetres()
        for app in list(restantes):
            libres = [h for h, exe in actuelles.items() if exe == app["processus"] and h not in trouvees]
            neuves = [h for h in libres if h not in deja_la]
            tard = time.time() - debut > 8 and app["processus"] not in NAVIGATEURS
            if neuves or ((tard or app["existante"]) and libres):
                trouvees[(neuves or libres)[0]] = app
                restantes.remove(app)
    for app in restantes:
        print(f"Fenêtre non trouvée : {app['processus']}")

    # Les apps restaurent parfois leur ancienne position au démarrage : on place 2 fois
    if not trouvees:
        return
    for h, app in trouvees.items():
        if app["processus"] in NAVIGATEURS:
            retenir_fenetre(app["processus"], h)
    for attente in (1.5, 2.5):
        time.sleep(attente)
        for h, app in trouvees.items():
            placer(h, app)


def lancer_tout():
    """Lancement complet (musique, LED, voix, applis). Le fichier « en cours » permet à la
    fenêtre de réglages d'afficher Stop ; il est toujours retiré à la fin, même en cas d'erreur."""
    mu = CFG["musique"]
    if os.path.exists(FICHIER_STOP):
        os.remove(FICHIER_STOP)
    ARRET.clear()
    ARRET_LEDS.clear()
    with open(FICHIER_EN_COURS, "w") as f:               # la fenêtre de réglages affiche alors « Stop »
        f.write(str(os.getpid()))
    try:
        _lancer_tout(mu)
    finally:
        for fichier in (FICHIER_STOP, FICHIER_EN_COURS):
            try:
                os.remove(fichier)
            except OSError:
                pass


def _lancer_tout(mu):
    """Corps du lancement : musique et LED en parallèle, phrase dite par-dessus la musique
    baissée, applis (et onglets des webmails) ouvertes et placées, puis récap à l'écran."""
    musique = chemin_musique(mu["fichier"])
    if musique and CFG["leds"]["active"] and CFG["leds"].get("rythme", {}).get("actif") \
            and etat_prechargement(musique) != "pret":
        print("Rythme de la musique pas encore préchargé : le lancement attend la fin du préchargement")
        precharger_rythme(musique)

    # 1) Préparation en parallèle : la phrase de Runner et l'adresse des LED.
    #    On attend au plus 'attente_max' secondes ; au-delà, tout part quand même :
    #    phrase de secours pour la voix, et les LED suivront dès qu'elles seront trouvées.
    voix_prete, leds_pretes, depart = threading.Event(), threading.Event(), threading.Event()

    def preparer_la_voix():
        try:
            preparer_voix(rafraichir=False)
            voix_prete.set()
        except Exception as e:
            print(f"Préparation de la voix impossible : {e}")

    def leds():
        ips, ok = trouver_leds()
        if not ok:
            # Juste après l'allumage ou la sortie de veille, les LED mettent un moment à se
            # reconnecter au point d'accès : on réessaie pendant 60 s, sans retarder le reste.
            print("LED pas encore joignables : nouvelles tentatives pendant 60 s")
            debut = time.time()
            while not ok and time.time() - debut < 60 and not arret_leds_demande():
                leds_pretes.set()                # le lancement n'attend pas les LED
                time.sleep(3)
                nouvelles, ok = trouver_leds()
                ips = nouvelles or ips
            if ok:
                print(f"LED joignables après {time.time() - debut:.0f} s")
            else:
                print("LED injoignables après 60 s (allumées ? connectées au point d'accès ?)")
        leds_pretes.set()
        depart.wait()                            # attend le top départ commun
        if CFG["leds"].get("rythme", {}).get("actif") and musique:
            # Mode rythme : pas de motif, les LED s'allument pour la première fois sur la musique
            for _ in range(20):                  # la musique démarre juste après le top départ
                if _musique["lecteur"]:
                    break
                time.sleep(0.05)
            if arret_leds_demande():
                return
            if _musique["lecteur"] and rythme_leds(_musique["lecteur"], ips, musique):
                return
        animer_leds(ips, ok)

    if CFG["voix"]["active"]:
        threading.Thread(target=preparer_la_voix, daemon=True).start()
    else:
        voix_prete.set()
    fil_leds = None
    if CFG["leds"]["active"]:
        fil_leds = threading.Thread(target=leds, daemon=True)
        fil_leds.start()
    else:
        leds_pretes.set()

    fin = time.time() + float(CFG["systeme"].get("attente_max", 3.0))
    voix_prete.wait(max(0, fin - time.time()))
    leds_pretes.wait(max(0, fin - time.time()))
    fichier_voix = None
    if not voix_prete.is_set():
        print("Phrase principale pas prête à temps : phrase de secours")
        fichier_voix = voix_de_secours()
    if not leds_pretes.is_set():
        print("LED pas encore trouvées : elles suivront dès que possible")

    # 2) Top départ : musique, LED, applis ; la voix suit après son délai.
    depart.set()
    if musique:
        try:
            _musique["lecteur"] = Lecteur(musique, mu["volume_pct"] / 100).jouer()
            threading.Thread(target=surveiller_musique, args=(_musique["lecteur"],), daemon=True).start()
            threading.Thread(target=touches_d_arret, daemon=True).start()
        except Exception as e:
            print(f"Lecture de la musique impossible : {e}")
    if CFG["voix"]["active"] and (voix_prete.is_set() or fichier_voix):
        voix = threading.Timer(CFG["voix"]["delai"], parler, args=(fichier_voix,))
    else:
        voix = threading.Thread(target=lambda: None)
    voix.start()

    lancer_et_placer_apps()
    if CFG["infos"].get("recap"):
        try:
            ouvrir_recap()
        except Exception as e:
            print(f"Récapitulatif impossible : {e}")
    noter_lancement()                            # les mails déjà annoncés ne sont plus « nouveaux »
    if fil_leds:
        fil_leds.join(30)
    voix.join(60)
    # Le script reste (invisible) jusqu'à la fin du morceau, sinon la musique s'arrêterait.
    # Arrêt : touches du clavier, --stop, ou bouton Stop de la fenêtre de réglages.
    if _musique["lecteur"]:
        _musique["lecteur"].fini.wait()
    if fil_leds:
        fil_leds.join(3)                         # le mode rythme remet la couleur finale
    if arret_leds_demande():
        eteindre_leds()


# ----------------------------- Une seule écoute ----------------------------
# - Runner « normal » (lancé au démarrage de la session) : un seul à la fois, grâce à un
#   verrou Windows (mutex). Un deuxième lancement s'arrête tout de suite.
# - Un test (« Tester tout » ou « Mode réglage » de la fenêtre) peut tourner en même temps : il écrit
#   son numéro de processus dans FICHIER_PAUSE, et le Runner en arrière-plan ignore les claps
#   tant que ce test est en cours.
FICHIER_PAUSE = os.path.join(tempfile.gettempdir(), "runner_pause")
kernel32.CreateMutexW.restype = wintypes.HANDLE
_verrou = {}


def deja_en_ecoute():
    """True si un autre Runner « normal » tourne déjà ; sinon prend le verrou."""
    _verrou["h"] = kernel32.CreateMutexW(None, False, "Local\\RunnerClapLauncher")
    return ctypes.get_last_error() == 183           # ERROR_ALREADY_EXISTS


def processus_actif(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = wintypes.DWORD()
    kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    kernel32.CloseHandle(h)
    return code.value == 259                        # STILL_ACTIVE


def ecoute_en_pause():
    """True si un test est en cours dans un autre processus."""
    try:
        with open(FICHIER_PAUSE) as f:
            pid = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return False
    if pid == os.getpid():
        return False
    if processus_actif(pid):
        return True
    try:
        os.remove(FICHIER_PAUSE)                    # test terminé sans avoir nettoyé
    except OSError:
        pass
    return False


def mettre_les_autres_en_pause():
    """Le Runner en arrière-plan ignore claps et raccourci jusqu'à reprendre_les_autres() (ou
    la fin de ce processus)."""
    import atexit
    with open(FICHIER_PAUSE, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(reprendre_les_autres)


def reprendre_les_autres():
    try:
        with open(FICHIER_PAUSE) as f:
            if f.read().strip() == str(os.getpid()):
                os.remove(FICHIER_PAUSE)
    except OSError:
        pass


# ---------------------------- Détection clap -----------------------------
DEBUG = "--debug" in sys.argv
TAUX, TRAME = 16000, 64          # 16 kHz, trames de 4 ms
AVANT, APRES = range(-14, -2), range(15, 28)


def micros_dispo():
    """Noms des micros (sans doublons de pilotes)."""
    return sorted({d["name"] for d in sd.query_devices() if d["max_input_channels"]})


def choisir_micro():
    """Index du micro choisi (None : micro par défaut de Windows). Les pilotes sont essayés
    dans l'ordre MME, DirectSound puis WASAPI, le premier qui accepte 16 kHz est gardé."""
    nom = CFG["micro"]
    if not nom:
        return None
    ordre = {"MME": 0, "Windows DirectSound": 1, "Windows WASAPI": 2}
    candidats = sorted((i for i, d in enumerate(sd.query_devices())
                        if d["max_input_channels"] and nom.lower()[:25] in d["name"].lower()),
                       key=lambda i: ordre.get(sd.query_hostapis(sd.query_devices(i)["hostapi"])["name"], 9))
    for i in candidats:
        try:
            sd.check_input_settings(device=i, channels=1, samplerate=TAUX)
            return i
        except Exception:
            pass
    raise OSError(f"aucun micro utilisable contenant « {nom} »")


def mesures(env, brut, k):
    """(attaque, décroissance, brillance) du son fort à la trame k (mêmes calculs pour
    l'écoute et le calibrage)."""
    pic = env[k]
    attaque = pic / (np.mean([env[k + j] for j in AVANT]) + 1e-6)
    decroiss = np.mean([env[k + j] for j in APRES]) / pic
    return attaque, decroiss, brillance(np.concatenate([brut[k + j] for j in range(-1, 4)]))


_SPECTRE = {}                                    # longueur -> (fenêtre, aigus, tout sauf graves)


def brillance(x):
    """Part d'énergie au-dessus de 1,5 kHz (un clap est riche en aigus, une voix beaucoup moins)."""
    if len(x) not in _SPECTRE:
        freqs = np.fft.rfftfreq(len(x), 1 / TAUX)
        _SPECTRE[len(x)] = (np.hanning(len(x)), freqs > 1500, freqs > 100)
    fenetre, aigus, utile = _SPECTRE[len(x)]
    spectre = np.abs(np.fft.rfft(x * fenetre)) ** 2
    return spectre[aigus].sum() / (spectre[utile].sum() + 1e-12)


def attendre_double_clap():
    """'clap' au double clap, 'raccourci' au raccourci clavier, False à la limite de temps."""
    dt = CFG["detection"]
    limite = float(CFG["systeme"].get("ecoute_max_min", 10)) * 60
    fin_ecoute = time.time() + limite if limite > 0 else float("inf")
    micro = choisir_micro()
    print(f"Micro : {sd.query_devices(micro, 'input')['name']} — en écoute (Ctrl+C pour quitter)")
    flux = queue.Queue()
    env, brut = deque(maxlen=1000), deque(maxlen=1000)   # ~4 s de trames
    reste = np.zeros(0, np.float32)
    n = a_voir = blocs = 0
    fond = 1.0
    dernier_clap_trame, dernier_clap_t = -10**9, -100.0
    dernier_bloc = time.time()

    with sd.InputStream(device=micro, channels=1, samplerate=TAUX, blocksize=512,
                        callback=lambda data, *_: flux.put(data[:, 0].copy())):
        while True:
            if time.time() > fin_ecoute:
                return False
            if DECLENCHE.is_set():
                return "raccourci"
            try:
                bloc = flux.get(timeout=0.5)
                dernier_bloc = time.time()
            except queue.Empty:
                if time.time() - dernier_bloc > 10:  # plus aucun son reçu depuis 10 s
                    print("Le micro ne renvoie plus de son (débranché ?) : écoute arrêtée")
                    return False
                continue
            reste = np.concatenate([reste, bloc])
            k_max = len(reste) // TRAME
            trames = reste[:k_max * TRAME].reshape(-1, TRAME)
            reste = reste[k_max * TRAME:]
            env.extend(np.sqrt((trames ** 2).mean(axis=1)))
            brut.extend(trames)
            n += k_max

            if blocs % 8 == 0:                       # bruit de fond : recalculé toutes les ~0,25 s
                fond = np.percentile(env, 30) if len(env) > 50 else 1.0
            blocs += 1
            base = n - len(env)
            while a_voir + APRES.stop <= n:          # on attend 110 ms de "futur" pour juger
                i, k = a_voir, a_voir - base
                a_voir += 1
                if k + AVANT.start < 0 or i - dernier_clap_trame < 30:
                    continue
                pic = env[k]
                if (pic < dt["seuil_min"] or pic < dt["fond_min"] * fond
                        or pic < max(env[k + j] for j in range(-3, 4))):
                    continue
                attaque, decroiss, brill = mesures(env, brut, k)
                ok = (attaque >= dt["attaque_min"] and decroiss <= dt["decroissance_max"]
                      and brill >= dt["brillance_min"])
                if DEBUG:                           # console seulement (trop bavard pour le journal)
                    builtins.print(f"vol={pic:.3f} attaque={attaque:5.1f} decroiss={decroiss:.2f} "
                          f"brillance={brill:.2f}{'   <== CLAP' if ok else ''}")
                if not ok:
                    continue
                dernier_clap_trame, t = i, i * TRAME / TAUX
                if 0.12 <= t - dernier_clap_t <= dt["ecart_max"]:
                    if ecoute_en_pause():
                        print("Double clap ignoré : un test est en cours")
                        dernier_clap_t = -100.0
                        continue
                    return "clap"
                dernier_clap_t = t


# ------------------------------- Calibrage -------------------------------
# Limites des réglages (les mêmes que les curseurs de la fenêtre)
LIMITES = {"attaque_min": (2, 20), "decroissance_max": (0.05, 0.6), "brillance_min": (0.02, 0.5),
           "fond_min": (2, 20), "seuil_min": (0.005, 0.1)}


def enregistrer_micro(duree):
    """Enregistre 'duree' secondes au micro choisi (16 kHz, mono)."""
    x = sd.rec(int(duree * TAUX), samplerate=TAUX, channels=1, dtype="float32", device=choisir_micro())
    sd.wait()
    return x[:, 0]


def sons_forts(x):
    """Sons forts d'un enregistrement, mesurés exactement comme pendant l'écoute :
    [{'t', 'vol', 'fond', 'attaque', 'decroissance', 'brillance'}]."""
    n = len(x) // TRAME
    brut = x[:n * TRAME].reshape(-1, TRAME)
    env = np.sqrt((brut ** 2).mean(axis=1))
    sons, dernier = [], -10**9
    for k in range(max(50, -AVANT.start), n - APRES.stop):
        pic = env[k]
        if k - dernier < 30 or pic < 0.003 or pic < env[k - 3:k + 4].max():
            continue
        fond = np.percentile(env[max(0, k - 1000):k], 30)
        if pic < 3 * fond:
            continue
        attaque, decroiss, brill = mesures(env, brut, k)
        sons.append({"t": k * TRAME / TAUX, "vol": float(pic), "fond": float(pic / (fond + 1e-9)),
                     "attaque": float(attaque), "decroissance": float(decroiss), "brillance": float(brill)})
        dernier = k
    return sons


def calibrer(sons_claps, sons_parole):
    """Seuils qui reconnaissent les claps enregistrés en rejetant la parole. Chaque seuil est
    placé à mi-chemin (en proportion) entre la parole et le clap le moins marqué, puis resserré
    vers les claps seulement si des sons de parole passent encore.
    Parmi les sons forts de l'enregistrement des claps, les claps sont les plus forts.
    Renvoie (réglages, claps reconnus, nombre de claps, sons de parole acceptés à tort, total parole)."""
    if not sons_claps:
        raise ValueError("aucun son fort entendu pendant les claps")
    plus_fort = max(c["vol"] for c in sons_claps)
    claps = [c for c in sons_claps if c["vol"] >= 0.3 * plus_fort]
    if len(claps) < 3:
        raise ValueError(f"seulement {len(claps)} clap(s) repéré(s) : il en faut au moins 3")
    mesure = {"attaque_min": "attaque", "brillance_min": "brillance", "fond_min": "fond",
              "seuil_min": "vol", "decroissance_max": "decroissance"}
    positions = np.array([0.5, 0.65, 0.8, 0.9])     # 0 = au niveau de la parole, 1 = au niveau du clap
    candidats, passe = {}, []
    for r, m in mesure.items():
        maxi = r == "decroissance_max"              # seul critère où il faut rester EN DESSOUS
        clap = max(c[m] for c in claps) if maxi else min(c[m] for c in claps)
        voix = [p[m] for p in sons_parole]
        ref = (np.percentile(voix, 5) if maxi else np.percentile(voix, 95)) if voix else None
        if ref is not None and (ref > clap if maxi else ref < clap):
            ref = max(ref, 1e-4)                    # séparés : entre la voix et le clap
            seuils = ref * (clap / ref) ** positions
        else:                                       # pas séparés (ou pas de parole) : près du clap
            seuils = clap / (positions + 0.1) if maxi else clap * (positions + 0.1)
        candidats[r] = np.clip(seuils, *LIMITES[r])
        v = np.array(voix)
        passe.append((v[None, :] <= candidats[r][:, None]) if maxi else (v[None, :] >= candidats[r][:, None]))
    ordre = list(mesure)
    if sons_parole:
        tous = passe[0][:, None, None, None, None, :] & passe[1][None, :, None, None, None, :] \
            & passe[2][None, None, :, None, None, :] & passe[3][None, None, None, :, None, :] \
            & passe[4][None, None, None, None, :, :]
        acceptes = tous.sum(axis=-1)                 # parole acceptée à tort, par combinaison
        severite = sum(np.indices(acceptes.shape))   # 0 = tous les seuils à mi-chemin
        choix = np.unravel_index(np.lexsort((severite.ravel(), acceptes.ravel()))[0], acceptes.shape)
        faux = int(acceptes[choix])
    else:
        choix, faux = (0,) * len(ordre), 0
    reglages = {r: round(float(candidats[r][i]), 3) for r, i in zip(ordre, choix)}

    def reconnu(c):
        return (c["vol"] >= reglages["seuil_min"] and c["fond"] >= reglages["fond_min"]
                and c["attaque"] >= reglages["attaque_min"] and c["brillance"] >= reglages["brillance_min"]
                and c["decroissance"] <= reglages["decroissance_max"])
    return reglages, sum(map(reconnu, claps)), len(claps), faux, len(sons_parole)


def masquer_messages_bibliotheques():
    """Le décodeur MP3 (mpg123, via soundfile) écrit des avertissements sans gravité directement
    sur la sortie d'erreur (« part2_3_length too large… » : petites irrégularités de certains
    MP3, ignorées au décodage). On les masque, sans masquer les erreurs de Python."""
    try:
        sys.stderr.flush()
        copie = os.dup(2)
        nul = os.open(os.devnull, os.O_WRONLY)
        os.dup2(nul, 2)                          # ce que les bibliothèques C écrivent : ignoré
        sys.stderr = os.fdopen(copie, "w", buffering=1)   # ce que Python écrit : affiché
    except Exception:
        pass


# --------------------------------- Main ----------------------------------
def main():
    if "--stop" in sys.argv:
        configurer_journal("stop")
        demander_arret()
        return
    if "--wifi" in sys.argv:
        configurer_journal("wifi")
        activer_point_acces()
        return

    est_un_test = "--config" in sys.argv or DEBUG       # lancé par la fenêtre de réglages
    configurer_journal("test" if est_un_test else "écoute")
    _log.info("Démarrage" + (" du test" if est_un_test else " de l'écoute"))
    if est_un_test:
        mettre_les_autres_en_pause()
    elif deja_en_ecoute():
        print("Runner est déjà en écoute : ce lancement est annulé.")
        return
    else:                                       # en arrière-plan, sans retarder l'écoute
        threading.Thread(target=lambda: (migrer_tache_reveil(), reparer_raccourcis()), daemon=True).start()
    if CFG["systeme"]["point_acces"]:           # pour que les LED aient leur réseau
        threading.Thread(target=activer_point_acces, args=(180,), daemon=True).start()
    if CFG["voix"]["active"]:
        threading.Thread(target=preparer_voix_en_boucle, daemon=True).start()
    prechargement = None
    musique = chemin_musique(CFG["musique"]["fichier"])
    if musique and CFG["leds"]["active"] and CFG["leds"].get("rythme", {}).get("actif") \
            and etat_prechargement(musique) != "pret":
        prechargement = threading.Thread(target=precharger_rythme, args=(musique,), daemon=True)
        prechargement.start()
    raccourci = ecouter_raccourci()
    try:
        declenche = attendre_double_clap()
    except OSError as e:                         # micro absent : le raccourci reste possible
        print(f"Écoute du micro impossible : {e}")
        declenche = False
    if not declenche:
        if not raccourci:
            _log.warning(f"Aucun double clap pendant {CFG['systeme']['ecoute_max_min']:g} min : "
                         "écoute arrêtée pour économiser les ressources (relancée au prochain "
                         "démarrage ou à la sortie de veille).")
            builtins.print("Aucun double clap : écoute arrêtée.")
            return
        # Micro fermé ; le raccourci, lui, reste actif (sans aucun calcul en attendant)
        print("Écoute du micro arrêtée ; le raccourci clavier reste actif")
        DECLENCHE.wait()
        declenche = "raccourci"
    print("Double clap !" if declenche == "clap" else "Raccourci clavier !")
    if prechargement and prechargement.is_alive():
        print("Préchargement du rythme en cours : lancement bloqué jusqu'à la fin du préchargement")
        prechargement.join()
        print("Préchargement terminé : lancement")
    lancer_tout()
    print("Terminé.")


if __name__ == "__main__":
    masquer_messages_bibliotheques()
    try:
        main()
    except KeyboardInterrupt:
        pass
