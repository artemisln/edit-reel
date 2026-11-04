# Credits

## Sound effects

All sounds live in `plugins/edit-reel/skills/edit-reel/audios/`.

| Files | Source | License |
|---|---|---|
| `sfx_*.mp3` (15 files) | Generated from code by `plugins/edit-reel/skills/edit-reel/scripts/make-sfx.py`. No samples, no recordings. Rerun the script to rebuild them. | CC0 1.0, public domain |
| `trimmed_*.mp3` (6 files) | Shipped with v1 of this repo (April 2026). | See note below |

Note on the `trimmed_*` files: they are kept from v1 so existing setups keep working. If you know
the original library of one of them, open an issue or PR so it can be credited here.

Only sounds that can be given away go into this repo: no music, no sounds from games, apps or
brands, no downloads without a license on file.

## Code

- v1 language flag, SFX fallback and Whisper download timeout: [@Nonilas](https://github.com/Nonilas) (PR #1).
- Captions in your own voice pair well with [blader/humanizer](https://github.com/blader/humanizer) (not bundled).
