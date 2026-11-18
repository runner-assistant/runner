# Historique des versions

Le numéro de version suit la forme `majeure.mineure.correctif` : un correctif ne change que des
défauts, une version mineure ajoute des fonctions, une version majeure change le fonctionnement.
La version installée est affichée en bas du menu de la fenêtre de réglages.

## 1.0.0 — première version publique

**Lancement**
- Double clap ou raccourci clavier (Ctrl + Alt + R par défaut, actif toute la session).
- Écoute au démarrage de la session et à la sortie de veille ; micro fermé après 10 min sans clap.

**Au lancement**
- Musique, avec baisse du volume pendant la voix, fondu et arrêt au choix.
- LED Govee (réseau local) : motifs de démarrage, ou suivi du rythme de la musique (analyse préparée à l'avance).
- Voix : phrase en parties (accueil, heure, météo, prochain cours, nouveaux mails, fin), voix neuronales Microsoft, phrase de secours hors connexion.
- Applis ouvertes et placées sur l'écran choisi ; onglets et webmails ajoutés sans doublon.
- Récap à l'écran : cours du jour et nouveaux mails.

**Infos**
- Météo (Open-Meteo), emploi du temps (lien ou fichier .ics), mails en IMAP (Gmail avec un mot de passe d'application) ou par connexion Google en lecture seule.
- Mots de passe gardés par Windows (Gestionnaire d'identification), jamais dans un fichier.

**Fenêtre de réglages**
- Tous les réglages sans toucher au code, avec des tests partie par partie.
- Calibrage automatique de la détection (5 doubles claps et un peu de parole) et mode réglage pour voir ce que le micro entend.
- Aide intégrée (la documentation), journal, thème sombre.

**Installation**
- `installer.bat` : installe ce qui manque (Python, bibliothèques), crée le raccourci, et sert de réparation.
- `desinstaller.bat` : retire Runner sans laisser de trace.
