# Runner — documentation

Tous les réglages de la fenêtre `clap_config.py`, page par page. Entre parenthèses : la clé correspondante dans `config.json`.

**Sommaire :** [Déroulement](#déroulement) · [La fenêtre](#la-fenêtre) · [Apps](#apps) · [LED](#led) · [Voix](#voix) · [Infos](#infos--emploi-du-temps-et-mails) · [Musique](#musique) · [Détection](#détection) · [Système](#système) · [Journal](#journal) · [Fichiers](#fichiers-et-données)

---

## Déroulement

1. **Écoute.** Runner écoute le micro et prépare à l'avance sa phrase (refaite chaque minute). Il active le point d'accès Wi-Fi si c'est demandé.
2. **Déclenchement :** un double clap, ou le raccourci clavier (Ctrl + Alt + R par défaut).
3. **Préparation, quelques secondes au plus** (« Attente max ») : la phrase et l'adresse des LED. Si la phrase n'est pas prête, c'est la phrase de secours qui est dite. Si les LED ne répondent pas, le reste part sans elles, et elles suivent dès qu'elles répondent.
4. **Top départ :** musique, LED et apps en même temps. Le webmail s'ouvre dans le navigateur s'il est demandé.
5. **Voix :** après « Délai après la musique ». La musique baisse pendant qu'elle parle.
6. **Placement** des fenêtres, puis **récap** à l'écran (cours du jour, mails) s'il est activé.
7. **Fin :** Runner reste actif, sans fenêtre, jusqu'à la fin de la musique.

**Arrêter la musique :** touche Lecture/Pause ou Stop du clavier, **Ctrl + Alt + M**, le bouton **Stop** de la fenêtre, ou `python clap_launcher.py --stop`. Les LED restent allumées.

**Sans déclenchement :** au bout de « Arrêt de l'écoute sans clap » (10 min), le micro est fermé. Le raccourci clavier, lui, reste actif. Si le micro ne renvoie plus aucun son pendant 10 s (débranché), l'écoute s'arrête avec une alerte dans le journal.

---

## La fenêtre

| Élément | Rôle |
|---|---|
| **Enregistrer** | Écrit les réglages dans `config.json`. Applique aussi le lancement au démarrage, la sortie de veille et les mots de passe mail. |
| **Tester tout** | Lance Runner comme à l'allumage du PC (écoute, double clap, tout le reste), avec **les réglages affichés, même non enregistrés**. |
| **Boutons ▶ des pages** | Testent une seule partie : apps, LED, rythme, voix, musique, emploi du temps, mails… |
| **Stop** | N'apparaît que pendant un test ou une musique lancée par Runner. Coupe tout. Il n'éteint les LED que si le test les utilisait. |
| **Ligne d'état** | En bas à gauche : ce qui est en cours et le résultat. |

Les réglages sans effet dans le mode choisi sont **grisés** (par exemple le motif des LED en mode rythme).

---

## Apps

Une ligne par app : **App** (liste des apps trouvées sur le PC, ou « Autre… » pour n'importe quel `.exe`), **Arguments / onglets**, **Écran** (`principal` ou `secondaire`), **Position** (menu façon Windows 11 : les emplacements déjà pris sont grisés).

- **Navigateurs :** la case « onglets » ouvre une liste d'adresses, une par ligne (`https://` est ajouté tout seul). Elles s'ouvrent dans une seule nouvelle fenêtre.
- **App déjà ouverte :** elle n'est pas relancée, sa fenêtre est replacée.
- **Navigateur déjà ouvert :** pas de nouvelle fenêtre ; seuls les onglets absents sont ajoutés (reconnus à leur titre).
- **Positions** (`zone`) : `plein`, `gauche_moitie`, `droite_moitie`, `gauche_2tiers`, `droite_1tiers`, `gauche_1tiers`, `droite_2tiers`, `centre_1tiers`.
- Dans `config.json`, `exe` accepte les variables Windows (`%LOCALAPPDATA%`), les jokers (`*`) et plusieurs chemins séparés par `|` : le premier trouvé est utilisé.

---

## LED

LED Govee pilotées en réseau local : active **« LAN Control »** dans l'app Govee Home, et mets les LED et le PC sur le même réseau (le point d'accès du PC, page Système, convient).

| Réglage | Rôle |
|---|---|
| **Allumer les LED** (`leds.active`) | Active la partie LED. |
| **Motif de démarrage** (`leds.motif`) | `fixe`, `arc-en-ciel`, `pulsation`, `clignotement` ou `fondu`. |
| **Couleur finale** (`leds.couleur`) | Couleur de fin, et couleur des flashs en mode rythme monochrome. |
| **Luminosité** (`leds.luminosite`) | 1 à 100 % ; maximum des flashs en mode rythme. |
| **Durée du motif** (`leds.duree`) | 0 à 10 s ; 0 = couleur finale tout de suite. |
| **Adresse IP** (`leds.ip`) | « Rechercher » la trouve. Runner la met à jour tout seul si elle change. |
| **Suivre le rythme de la musique** (`leds.rythme.actif`) | Remplace le motif : les LED s'allument sur le premier coup de la musique, puis clignotent sur ses coups. |
| **Couleurs** (`leds.rythme.mode`) | `mono` (couleur finale) ou `couleurs` (la teinte change au fil des coups). |
| **Sensibilité** (`leds.rythme.sensibilite`) | Plus haut = plus de coups suivis. |
| **Avance des LED** (`leds.rythme.avance_ms`) | Compense le retard des LED. À augmenter si elles réagissent après le son. |
| **Éteindre pendant les silences** (`leds.rythme.eteindre_silences`) | Sinon, luminosité minimum. Éteindre ne les abîme pas. |

**Mode rythme, en bref.** Le morceau est analysé une seule fois, en quelques secondes (« préchargement »), et le résultat est gardé dans `cache_rythme`. Une pastille à côté de la musique indique l'état : « ● préchargé », « ◌ en cours » ou « ○ à faire ». Le préchargement se fait tout seul, et un lancement attend qu'il soit terminé. Pendant la musique, Runner suit un programme prêt d'avance, calé sur ce qu'on entend, avec au plus 6 commandes par seconde :
- **un flash au maximum sur chaque coup marqué, puis une retombée au minimum** ;
- **les séries rapides** (moins de 0,33 s entre deux coups) sont rendues fort / faible / fort ;
- **les silences et les arrêts du riff** éteignent les LED, qui se rallument juste avant le coup suivant.

L'intensité passe par la luminosité : les Govee ignorent une couleur « assombrie ».

**Fiabilité.** L'état final est vérifié auprès des LED (jusqu'à 3 essais). Juste après l'allumage du PC, Runner réessaie de les joindre pendant 60 s. Si elles s'allument mais que le journal indique « sans réponse », c'est le pare-feu qui bloque leurs réponses : autorise Python sur les réseaux privés.

---

## Voix

| Réglage | Rôle |
|---|---|
| **Runner parle au démarrage** (`voix.active`) | Active la voix. |
| **Voix** (`voix.voix`) | Voix neuronales Microsoft. ▶ fait écouter la phrase actuelle. |
| **Ville (météo)** (`voix.ville`) | Ses coordonnées sont retrouvées toutes seules. |
| **Phrase principale** (`voix.parties`) | 6 parties, dites dans l'ordre. Chacune peut être cochée ou non, et son texte modifié. |
| **Phrase de secours** (`voix.secours`) | Dite si la phrase principale n'est pas prête à temps. |
| **Délai après la musique** (`voix.delai`) | Temps entre le début de la musique et la voix. |

| Partie | Texte par défaut | Variables |
|---|---|---|
| Accueil | `Bonjour Monsieur.` | — |
| Heure | `Il est {heure}.` | `{heure}` (« 14 heures 5 », « midi ») |
| Météo | `Il fait {temperature} degrés à {ville}, avec {ciel}.` | `{temperature}`, `{ciel}`, `{ville}` |
| Cours | `Votre prochain cours, {cours}, commence à {heure_cours}{salle}.` | `{cours}`, `{heure_cours}`, `{salle}` (« , en Amphi B ») |
| Mails | `Vous avez {nb_mails} nouveaux mails, dont le dernier de {expediteur}.` | `{nb_mails}` (« 3 », « plus de 50 »), `{expediteur}`, `{objet}` (du dernier nouveau mail) |
| Fin | `Votre espace de travail est prêt.` | — |

**La partie Mails a trois phrases**, réglables avec le bouton « Autres cas… » : une quand il y a **plusieurs** nouveaux mails (celle de la ligne), une pour **un seul** (`Vous avez un nouveau mail, de {expediteur}.`) et une pour **aucun** (`Aucun nouveau mail.` ; vide = rien n'est dit).

**Une partie est sautée** si elle est décochée ou vide, ou si son information manque : pas de météo, plus de cours aujourd'hui, mails non configurés. L'aperçu sous les parties montre la phrase complète (avec des exemples si besoin).

La voix neuronale et la météo (Open-Meteo, gratuit, sans compte) ont besoin d'Internet. Sans Internet, la phrase de secours est dite par la voix intégrée de Windows.

---

## Infos : emploi du temps et mails

### Emploi du temps

| Réglage | Rôle |
|---|---|
| **Annoncer le prochain cours** (`infos.agenda.actif`) | Active la partie « Cours » de la phrase et du récap. |
| **Lien du calendrier (.ics)** (`infos.agenda.lien`) | Lien d'export de ton emploi du temps (`https://` ou `webcal://`). |

**Trouver le lien dans ADE :** ouvre ton emploi du temps, clique sur le bouton d'export (icône calendrier, « Export agenda » ou « Exporter »), choisis une période assez longue (le semestre), puis copie le lien proposé.

Le calendrier est relu au plus toutes les 30 min. Sans connexion, la dernière version téléchargée sert.

### Mails

| Réglage | Rôle |
|---|---|
| **Annoncer les nouveaux mails** (`infos.mails.actif`) | Active la partie « Mails » de la phrase et du récap. |
| **Comptes** (`infos.mails.comptes`) | Une ligne par boîte. **Gmail** : bouton « Se connecter avec Google ». **Autres boîtes** : adresse, serveur IMAP et mot de passe ; une fois le mot de passe enregistré, la case laisse la place à un bouton « Déconnecter », qui l'efface. Pour toutes : un nom et l'adresse du webmail. Boutons « + Gmail » et « + Autre boîte mail ». |
| **Ouvrir les webmails au lancement** (`infos.ouvrir_webmail`) | Ajoute l'onglet de chaque webmail dans le premier navigateur de la page Apps. |
| **Afficher le récap à l'écran** (`infos.recap`) | Petite fenêtre en haut à droite : cours restants de la journée, et pour chaque boîte le nombre de nouveaux mails (et, en petit, le total des non lus), les 5 derniers nouveaux (expéditeur et objet), et un bouton pour ouvrir le webmail. |

- **Nouveaux mails :** les mails non lus de la boîte de réception arrivés **depuis le dernier lancement de Runner** (au plus 7 jours ; les dernières 24 h au tout premier lancement). Le total des non lus, souvent des milliers, n'est pas annoncé. Au-delà de 50, Runner dit « plus de 50 nouveaux mails ».
- **Lecture seule :** rien n'est marqué comme lu. Les boîtes sont relues au plus toutes les 5 min.
- **Sécurité :** mots de passe et connexions Google sont gardés par Windows, dans le Gestionnaire d'identification (chiffrés, liés à ta session Windows). Ils ne sont **jamais** écrits dans `config.json`. Ils apparaissent dans *Panneau de configuration › Gestionnaire d'identification › Informations d'identification Windows* sous le nom `Runner:…`. Supprimer un compte avec ✕ les efface aussi (et retire l'autorisation chez Google pour Gmail).

#### Gmail : « Se connecter avec Google »

Runner utilise la connexion officielle de Google (OAuth). Tu te connectes une fois dans ton navigateur, et Runner reçoit seulement une autorisation de **lecture** de tes mails (`gmail.readonly`) : ni mot de passe, ni droit d'envoyer ou de supprimer. « Déconnecter » retire cette autorisation chez Google. Tu peux aussi la retirer depuis ton compte Google (Sécurité › Applications tierces).

**Préparation, une seule fois (environ 10 min)** : il faut un « ID client OAuth » Google, gratuit.
1. Sur [console.cloud.google.com](https://console.cloud.google.com), crée un projet (par exemple « Runner »).
2. *API et services › Bibliothèque* : cherche **Gmail API**, puis **Activer**.
3. *Google Auth Platform* (ou *Écran de consentement OAuth*) : type **Externe**, nom de l'app « Runner », ton adresse mail comme contact.
4. Dans *Branding*, ne remplis que le nom et les deux adresses mail. **N'ajoute pas de logo** : un logo oblige à faire valider l'app par Google. Puis, dans *Audience*, clique sur **Publier l'application** (statut « En production »). En statut « Test », Google oblige à se reconnecter tous les 7 jours. Si Google refuse de publier sans liens, renseigne la page d'accueil, la confidentialité et les conditions avec les pages du projet en ligne (`README.md`, `PRIVACY.md`, `TERMS.md`).
5. *Clients* (ou *Identifiants*) › **Créer un ID client OAuth** › type **Application de bureau** › **Télécharger le JSON**.
6. Dans Runner : page Infos › **+ Gmail** › **Se connecter avec Google**, et choisis le fichier JSON. Il est copié dans le projet sous le nom `google_client.json`.
7. Google affiche « Google n'a pas validé cette application ». C'est normal pour une app personnelle : clique sur *Paramètres avancés › Accéder à Runner*, puis autorise la lecture des mails.

**Pour des amis :** donne-leur ton `google_client.json`, ou laisse chacun créer le sien. Une app non validée par Google accepte au plus 100 personnes en tout.

#### Autres boîtes (école, Outlook, fournisseur d'accès…) : IMAP

Il faut l'adresse du **serveur IMAP** de la messagerie. Elle est indiquée dans l'aide de ta messagerie, à la rubrique « configurer un client mail », « Thunderbird » ou « IMAP ». Le mot de passe tapé est enregistré dans Windows au clic sur « Enregistrer » ; la case est alors remplacée par le bouton « Déconnecter ». Certaines écoles bloquent IMAP (souvent avec Microsoft 365) : dans ce cas, garde seulement l'ouverture du webmail.

---

## Musique

| Réglage | Rôle |
|---|---|
| **Musique** (`musique.fichier`) | Fichiers du dossier du projet et de `musiques`, ou « Parcourir… ». Formats : mp3, wav, wma, m4a. |
| **Volume** (`musique.volume_pct`) | Volume de la musique. |
| **Pendant la voix** (`musique.pendant_voix_pct`) | Volume pendant que Runner parle (100 % = pas de baisse). |
| **Sortie audio** (`sortie_audio`) | « Auto » = la sortie Windows du moment. |
| **Jouer jusqu'à la fin** (`musique.jusqu_a_la_fin`) | Sinon, arrêt après la durée choisie. |
| **Sinon, arrêter après** (`musique.duree_max_s`) | 10 à 600 s. |
| **Fondu de fin** (`musique.fondu_fin_s`) | Baisse progressive avant l'arrêt (0 = coupure nette). |

---

## Détection

| Réglage | Rôle |
|---|---|
| **Micro** (`micro`) | Micro utilisé (« par défaut » = celui de Windows). |
| **Brillance min** (`detection.brillance_min`) | Part du son dans les aigus : un clap est brillant, la voix non. |
| **Attaque min** (`detection.attaque_min`) | Montée brutale du son par rapport aux 50 ms d'avant. |
| **Décroissance max** (`detection.decroissance_max`) | Son restant 60 à 110 ms après le pic : un clap retombe très vite. |
| **Au-dessus du bruit de fond** (`detection.fond_min`) | Combien de fois le pic dépasse le bruit ambiant. |
| **Volume minimum** (`detection.seuil_min`) | Volume minimal d'un clap. |
| **Écart max entre 2 claps** (`detection.ecart_max`) | Temps maximal entre les deux claps (minimum fixé à 0,12 s). |

**Calibrer automatiquement (recommandé).** Une fenêtre guide en deux étapes : tu tapes 6 fois dans tes mains, puis tu parles normalement pendant 8 s. Runner mesure tes claps et ta voix, et place chaque seuil **à mi-chemin entre les deux**. Il ne le resserre vers les claps que si des sons de ta voix passent encore. Le bilan indique combien de claps sont reconnus et combien de sons de ta voix seraient pris pour un clap. « Appliquer » remplit les réglages : pense ensuite à enregistrer. Pendant le calibrage, le Runner en arrière-plan est en pause.

**Valeurs par défaut** remet les six réglages d'origine. **Mode réglage** ouvre une console qui affiche les mesures de chaque son fort (`<== CLAP` quand il est accepté).

Si le micro n'entend pas les claps, désactive la **réduction de bruit** de son pilote : elle les efface souvent.

---

## Système

| Réglage | Rôle |
|---|---|
| **Lancer Runner à l'ouverture de session** (`systeme.demarrage_session`) | Raccourci dans le dossier Démarrage de Windows. |
| **Lancer Runner à la sortie de veille** (`systeme.reveil`) | Tâche planifiée `Runner\Reveil`. |
| **Point d'accès Wi-Fi au lancement** (`systeme.point_acces`) | Partage la connexion du PC pour les LED. Rien n'est touché s'il est déjà actif. |
| **Attente max avant lancement** (`systeme.attente_max`) | Temps maximal d'attente de la voix et des LED. |
| **Arrêt de l'écoute sans clap** (`systeme.ecoute_max_min`) | Fermeture du micro sans double clap (0 = jamais). |
| **Raccourci clavier** (`systeme.raccourci`) | Déclenche Runner comme un double clap : Ctrl + Alt + R, Ctrl + Alt + Espace, Ctrl + Maj + R, Win + Alt + R, Ctrl + Alt + F12, ou aucun. Il reste actif après la fermeture du micro, sans rien consommer. |

**Conseil :** dans *Paramètres › Point d'accès sans fil mobile*, désactive l'économie d'énergie, sinon Windows coupe le point d'accès quand rien n'y est connecté.

Les raccourcis (Bureau et démarrage) sont vérifiés et réparés à chaque démarrage. Ils passent par `pyw.exe`, qui suit les mises à jour de Python.

---

## Journal

Tout est noté dans `runner.log` : déclenchements, apps, LED, alertes (en jaune) et erreurs (en rouge). Chaque ligne indique qui écrit : `[écoute]`, `[test]`, `[réglages]`, `[récap]`… La page propose un filtre « Alertes et erreurs seulement », et les boutons « Effacer » et « Ouvrir le fichier ». Au-delà de 1 Mo, le journal est archivé dans `runner.ancien.log`.

---

## Fichiers et données

**`config.json`** est créé au premier enregistrement. Toute clé absente prend sa valeur par défaut.
- **Enregistrement sûr :** fichier temporaire puis remplacement en une seule opération ; la version précédente est gardée dans `config.json.bak`.
- **Fichier abîmé :** Runner reprend la copie de secours, ou les valeurs par défaut, et met le fichier abîmé de côté dans `config.illisible.json`.
- **Valeur invalide :** seule cette valeur est remplacée par sa valeur par défaut. C'est signalé dans le journal.
- **Contenu personnel :** ville, adresse des LED, lien de l'emploi du temps, adresses mail. **Ne le partage pas tel quel.** Les mots de passe n'y sont jamais.

**`google_client.json`** : ton ID client Google (connexion Gmail). Ne le publie pas en ligne ; tu peux le donner à des amis.

**`cache_rythme\`** : analyses des musiques. Les analyses périmées sont supprimées toutes seules, et le dossier peut être supprimé sans risque.

**Dossier temporaire de Windows (`%TEMP%`)** : fichiers `runner_*` (phrase préparée, signal d'arrêt, emploi du temps et récap en cache, pause pendant un test…). Tous peuvent être supprimés sans risque.

**Commandes (dans le dossier du projet) :** `python clap_launcher.py` (écoute, avec console), `--stop` (arrête la musique), `--wifi` (active le point d'accès).
