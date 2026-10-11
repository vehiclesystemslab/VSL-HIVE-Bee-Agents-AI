# VSL-HIVE Bee Agents AI v0.1

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22948989.svg)](https://doi.org/10.5281/zenodo.22948989)

`Agents are disposable; evidence and knowledge persist.`

## Reference release

- DOI: [10.5281/zenodo.22948989](https://doi.org/10.5281/zenodo.22948989)
- Bee: `JP-ALPHA-BEE-003`
- Territory: `JP`
- Source: `JMA_EQVOL`
- Source organization: Japan Meteorological Agency
- Lifecycle: `SEED -> SLEEP -> WAKE -> FORAGE -> DEPOSIT -> DIE`
- Transport: TLS 1.3 / mutual authentication

## Independent LIVE node candidate — JP-02 NRA Nuclear

The repository now includes an isolated HIVE node for the Nuclear Regulation Authority of Japan (NRA), built to observe the official NRA Nuclear Emergency Alert surface directly.

Public node path:

- `nodes/jp-nra-nuclear-v0_1/`

Operationally validated properties:

- direct official NRA source observation
- fail-closed classification
- silence on drills, `異常なし`, no-impact notices, and ambiguous wording
- WAKE only on explicit positive NRA incident/impact wording
- independent Observer, Bee, CORE, runtime state, evidence chain, and failure domain
- mTLS between Bee and CORE
- restart-safe Honey-chain continuity
- persistent systemd operation
- real VM reboot recovery
- Observer readiness guard
- off-node CA signing-key custody; CA private key absent from the node runtime
- external/X publication disabled

The JP-02 branch and pull request remain candidate/review artifacts until merge is explicitly approved. The published JMA v0.1 reference release and its hashes remain unchanged.

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

JP-02 NRA primary source:

https://kinkyu.nra.go.jp/

## Verify

`SHA256SUMS.txt` belongs to the immutable JMA v0.1 reference release. Because this top-level README now also surfaces JP-02, verify the unchanged legacy artifacts while excluding only the historical README entry:

```bash
grep -v ' ./README.md
python3 -c "import ast; ast.parse(open(\"reference/vsl_hive_bee_agent_reference_v0_1.py\").read())"
python3 -c "import ast; ast.parse(open(\"reference/vsl_hive_core_reference_v0_1.py\").read())"
```

No credentials, private keys, private network bindings, or cloud credentials are included.
 SHA256SUMS.txt | sha256sum -c -
python3 -c "import ast; ast.parse(open(\"reference/vsl_hive_bee_agent_reference_v0_1.py\").read())"
python3 -c "import ast; ast.parse(open(\"reference/vsl_hive_core_reference_v0_1.py\").read())"
```

No credentials, private keys, private network bindings, or cloud credentials are included.
