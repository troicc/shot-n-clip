# V3 editorial quality workflow

The deterministic V3 validator does not call an LLM. Claude Code or another coding agent produces the semantic JSON artifacts; the local CLI verifies them.

## Pipeline

```text
source_map.json
→ editorial_inputs/chunks
→ candidate_pool.json
→ selection_audit.json
→ packs/<pack-id>/editorial_pack.json
→ packs/<pack-id>/translation_audit.json
→ strict validation
→ render
```

## Commands

```bash
bin/qcard-quality prepare work/<video-id>
bin/qcard-quality validate-candidates work/<video-id>
bin/qcard-quality validate-selection work/<video-id>
bin/qcard-quality validate-translation work/<video-id> --pack pack-01
bin/qcard-quality validate work/<video-id> --strict
```

In Claude Code:

```text
/native-subtitle-quote-image '<youtube-url>' --packs auto --max-packs 4 --mode all --copy both --quality strict
```

A ready pack must contain 5–6 non-redundant quotes, pass independent selection review, preserve source claim units, have an empty fidelity ledger, and pass all native-Chinese checks.
