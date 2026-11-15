# Podcast « Conteur d'Afrique »

Version audio de la chaîne Conteur d'Afrique. **Un épisode = une histoire complète** (toutes les parties d'un conte ou d'un héros, ou une vidéo Excellence), publié seulement quand sa dernière partie est déjà sortie sur les réseaux. Les histoires ne sont jamais mélangées.

- Flux RSS : https://williams335.github.io/conteur-dafrique-podcast/feed.xml (à ajouter une fois dans Spotify for Creators, Apple Podcasts, Deezer, Amazon Music).
- Chaque jour, `.github/workflows/podcast.yml` lance `scripts/build.py` : lecture de Notion, assemblage des parties (ffmpeg), ajout dans `docs/episodes/`, régénération de `docs/feed.xml`.
- Réglages : `podcast.json`. Le jeton Notion est un secret GitHub (`NOTION_TOKEN`), jamais dans les fichiers.
