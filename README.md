# VSL-HIVE Bee Agents AI v0.1

`Agents are disposable; evidence and knowledge persist.`

## Reference release

- Bee: `JP-ALPHA-BEE-003`
- Territory: `JP`
- Source: `JMA_EQVOL`
- Source organization: Japan Meteorological Agency
- Lifecycle: `SEED -> SLEEP -> WAKE -> FORAGE -> DEPOSIT -> DIE`
- Transport: TLS 1.3 / mutual authentication

## Validated evidence

| Gate | Status |
| --- | --- |
| G07E | `PASS_G07E_LIVE_PAIR_STATIC_CROSS_AUDIT` |
| G07J | `PASS_G07J_LIVE_NO_CHANGE` |
| G07K | `PASS_G07K_POST_OBSERVATION_SILENCE_INTEGRITY` |

## Public reference artifacts

- `reference/vsl_hive_bee_agent_reference_v0_1.py`
- `reference/vsl_hive_core_reference_v0_1.py`
- `contracts/flower.schema.json`
- `contracts/honey.schema.json`
- `evidence/EVIDENCE_MANIFEST.json`
- `SHA256SUMS.txt`

## Source

https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml

## Verify

```bash
sha256sum -c SHA256SUMS.txt
python3 -c "import ast; ast.parse(open(\"reference/vsl_hive_bee_agent_reference_v0_1.py\").read())"
python3 -c "import ast; ast.parse(open(\"reference/vsl_hive_core_reference_v0_1.py\").read())"
```

No credentials, private keys, private network bindings, or cloud credentials are included.
