# Third-Party Notices

## baoyu-youtube-transcript

- **Source:** <https://github.com/JimLiu/baoyu-skills>, directory
  `skills/baoyu-youtube-transcript/`
- **Use:** YouTube metadata and caption retrieval only.
- **License:** MIT. The copied Skill keeps its upstream LICENSE.
- **Modifications:** No core upstream transcript logic is modified by this
  project.

## native-subtitle-quote-image — design reference

- **Source:** <https://github.com/chengyi-ai/native-subtitle-quote-image>
- **Reviewed revision:** public `main` tree
  `f1fa5b70448f620ea92179357eca4b0222481b9d`
- **License:** MIT for that repository's code and Skill instructions.
- **How it informed V4:** its production constraints—1440×1920 3:4 output,
  five time points at most, chronological nearby subtitle moments, exact frame
  extraction, contact-sheet review and JPEG 4:4:4 export—were used as design
  references.
- **Code use:** shot-n-clip does not copy its embedded-subtitle renderer. V4
  independently renders verified Chinese/English text and retains this
  project's source, translation and selection audits.

## Python runtime dependencies

| Package | Purpose | License |
|---|---|---|
| Pillow | deterministic image rendering | MIT-CMU |
| PyYAML | style/config loading | MIT |
| yt-dlp | source video download | Unlicense |

System dependencies include FFmpeg/FFprobe. Fonts are discovered from the host
system and are never copied or redistributed by this repository.
