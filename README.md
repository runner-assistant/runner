# Runner

**Tape deux fois dans tes mains, et ton poste se prépare tout seul.** Ta musique démarre, tes LED s'allument (et peuvent clignoter au rythme de la musique). Une voix te donne l'heure, la météo, ton prochain cours et tes mails non lus, et tes apps s'ouvrent, chacune placée au bon endroit sur tes écrans.

Pas besoin de taper dans tes mains ? Un raccourci clavier (**Ctrl + Alt + R**) fait la même chose.

Tout se règle depuis une fenêtre, sans toucher au code. Le détail de chaque réglage est dans [`DOCUMENTATION.md`](DOCUMENTATION.md).

---

## Installation (5 minutes)

Runner fonctionne sous **Windows 10 ou 11** uniquement.

**1. Installer Python** (3.10 ou plus récent), dans un terminal :
```
winget install Python.Python.3.13
```
Tu peux aussi l'installer depuis python.org : coche alors **« Add python.exe to PATH »**. Ferme ensuite le terminal et rouvre-le.

**2. Installer les 4 bibliothèques :**
```
pip install -U sounddevice numpy soundfile edge-tts
```
Si `pip` n'est pas reconnu, utilise `python -m pip install -U sounddevice numpy soundfile edge-tts`.

**3. Copier les fichiers** du projet dans un dossier, par exemple `C:\Runner`, et ranger tes musiques dans un sous-dossier `musiques`.

**4. Ouvrir la fenêtre de réglages :**
```
cd C:\Runner
python clap_config.py
```
Un raccourci **« Runner - réglages »** est créé sur le Bureau pour les fois suivantes.

**Vérifier que tout est installé :**
```
python -c "import tkinter, sounddevice, numpy, soundfile, edge_tts; print('Tout est installé')"
```

---

## Premier réglage

1. **Détection** : choisis ton micro, puis clique sur **Calibrer automatiquement** (6 claps, puis 8 s de parole).
2. **Apps** : ajoute tes apps, choisis l'écran et la position de chacune.
3. **Musique** et **Voix** : choisis ta musique, ta voix et le texte de la phrase.
4. *(Optionnel)* **LED** : active « LAN Control » dans l'app Govee Home, puis clique sur « Rechercher ».
5. *(Optionnel)* **Infos** : colle le lien de ton emploi du temps (.ics) et ajoute tes boîtes mail.
6. **Système** : coche « Lancer Runner à l'ouverture de session ».
7. Clique sur **Enregistrer**, puis sur **Tester tout**, et tape deux fois dans tes mains.

---

## Au quotidien

| Pour… | Fais… |
|---|---|
| Lancer Runner | Double clap, ou **Ctrl + Alt + R** (modifiable dans Système) |
| Arrêter la musique | Touche Lecture/Pause ou Stop du clavier, **Ctrl + Alt + M**, ou le bouton Stop de la fenêtre |
| Changer un réglage | Raccourci « Runner - réglages » du Bureau, puis **Enregistrer** |
| Voir ce qui s'est passé | Page **Journal** de la fenêtre |

Runner écoute le micro 10 min après l'ouverture de session (ou la sortie de veille), puis le ferme. Le raccourci clavier reste disponible ensuite.

---

## En cas de problème

| Problème | Solution |
|---|---|
| Les claps ne sont pas détectés, ou ta voix déclenche Runner | Page Détection : **Calibrer automatiquement**. Désactive aussi la réduction de bruit du pilote du micro, qui efface souvent les claps. |
| Les LED ne s'allument pas | « LAN Control » activé dans Govee Home ? LED et PC sur le même réseau ? Sur un réseau d'école (eduroam), utilise le point d'accès du PC (page Système). |
| Les LED s'allument, mais le journal dit « sans réponse » | Le pare-feu bloque leurs réponses : autorise Python sur les réseaux privés. |
| Le raccourci du Bureau ne marche plus | `cd C:\Runner` puis `python clap_config.py` : la fenêtre répare les raccourcis. |
| Après une mise à jour de Python | Réinstalle les bibliothèques : `pip install -U sounddevice numpy soundfile edge-tts`. |
| Gmail : « connexion Google expirée » | Page Infos : **Se connecter avec Google** à nouveau. Si ça revient chaque semaine, ton projet Google est resté en statut « Test » : publie-le (voir DOCUMENTATION, page Infos). |
| La voix ne parle pas, ou dit la phrase de secours | La voix neuronale a besoin d'Internet. Sans Internet, Runner utilise la voix de Windows. |

---

## Fichiers

| Fichier | Rôle |
|---|---|
| `clap_launcher.py` | Le programme : écoute, détection, lancement. |
| `clap_config.py` | La fenêtre de réglages. |
| `config.json` | Tes réglages (créé au premier enregistrement). Il contient des informations personnelles : ne le partage pas. |
| `runner.log` | Le journal. |
| `musiques\` | Tes musiques (mp3, wav, wma, m4a). |
| `cache_rythme\` | Analyses des musiques pour le mode rythme des LED (recréées au besoin). |
| `google_client.json` | Ton ID client Google, pour la connexion Gmail (créé à la première connexion). Ne le publie pas. |

**Confidentialité :** tout reste sur ton PC. Gmail passe par la connexion officielle de Google, en lecture seule, sans mot de passe dans Runner. Les mots de passe des autres boîtes sont gardés par Windows (Gestionnaire d'identification), jamais dans un fichier du projet. Runner se connecte seulement à la météo (Open-Meteo), à la voix (Microsoft Edge TTS), à ton emploi du temps et à tes boîtes mail.

**Mise à jour depuis l'ancien nom (Jarvis) :** le journal, les raccourcis et la tâche de sortie de veille sont repris automatiquement.

---

## Licence

Ce projet est **open source**, sous **licence MIT**. Tu peux librement l'utiliser, le copier, le modifier, le fusionner avec d'autres projets, le publier, le distribuer, le vendre ou l'intégrer à un produit, **à des fins privées comme commerciales**.

```
MIT License

Copyright (c) 2026 Timothée Adjanohoun

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

La licence couvre le code du projet, pas les fichiers que tu y ajoutes. Les musiques restent soumises à leurs propres droits, et les voix edge-tts aux conditions d'utilisation de Microsoft.
