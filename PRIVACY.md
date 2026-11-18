# Runner — Politique de confidentialité

*Dernière mise à jour : 18 novembre 2026*

Runner est un logiciel libre qui s'exécute **uniquement sur ton ordinateur** (Windows). Il n'a ni serveur, ni compte utilisateur, ni statistiques d'utilisation. Son auteur ne reçoit aucune de tes données.

## Données Google (Gmail)

Si tu choisis « Se connecter avec Google », Runner demande une seule autorisation : **la lecture de tes mails** (`https://www.googleapis.com/auth/gmail.readonly`).

- **Ce qui est lu :** le nombre de mails non lus de ta boîte de réception, ainsi que l'expéditeur et l'objet des 5 derniers mails non lus. Le contenu des mails n'est jamais lu.
- **À quoi ça sert :** uniquement à t'annoncer ces informations au lancement de Runner (phrase dite à voix haute et petite fenêtre récapitulative sur ton écran).
- **Ce qui n'est jamais fait :** Runner n'envoie, ne modifie, ne supprime et ne marque comme lu aucun mail.
- **Conservation :**
  - Le jeton d'autorisation est gardé dans le Gestionnaire d'identification de Windows, chiffré et lié à ta session.
  - Le récapitulatif (expéditeurs et objets) est gardé quelques minutes dans le dossier temporaire de Windows, puis remplacé.
  - Rien d'autre n'est conservé.
- **Partage :**
  - Ces données ne sont ni vendues, ni utilisées pour de la publicité, ni transmises à l'auteur de Runner.
  - Seule exception : la phrase dite à voix haute, qui peut contenir le nom d'un expéditeur, est convertie en voix par le service de synthèse vocale de Microsoft (Edge TTS). C'est le cas uniquement si la voix est activée.
- **Révocation :** à tout moment, avec le bouton « Déconnecter » de Runner, ou depuis ton compte Google (Sécurité › Applications tierces).

L'utilisation des informations reçues des API Google respecte le [Règlement sur les données utilisateur des services d'API Google](https://developers.google.com/terms/api-services-user-data-policy), y compris les exigences d'utilisation limitée (*Limited Use*).

## Autres données

| Donnée | Où elle va |
|---|---|
| Phrase d'accueil (heure, météo, cours, mails) | Service de synthèse vocale Microsoft (Edge TTS), pour être convertie en voix |
| Ville choisie | Open-Meteo, pour la météo |
| Lien de ton emploi du temps | Le serveur de ton établissement, pour le télécharger |
| Autres boîtes mail (IMAP) | Uniquement leur propre serveur ; le mot de passe est gardé par Windows |
| Réglages (`config.json`) et journal (`runner.log`) | Restent sur ton ordinateur |

## Contact

Pour toute question : runner.assistant@gmail.com
