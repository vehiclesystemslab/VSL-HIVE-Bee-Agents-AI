# HIVE Japan NRA Nuclear Node v0.1

Independent HIVE node for the Nuclear Regulation Authority of Japan (NRA).

## Objective

Observe the official NRA Nuclear Emergency Alert surface and remain silent unless NRA explicitly communicates a real, relevant nuclear-facility impact or incident.

## Safety / publication policy

The node is fail-closed.

SILENCE:
- no NRA notice
- exercise / drill (`訓練`)
- `異常なし` / no abnormality
- inspection or assessment without confirmed impact
- ambiguous wording
- fetch/parse failure

WAKE:
- only when the official NRA content contains an explicit positive impact/incident marker and no exclusion marker.

## Isolation

This node does not modify or depend operationally on `JP-ALPHA-BEE-003`.
It has its own:
- observer
- Flower contract
- Bee runtime
- Honey contract
- CORE receiver
- runtime state
- evidence directory
- public-event output

## Lifecycle

`SLEEP -> WAKE -> FORAGE -> DEPOSIT -> SLEEP`

## Source

Primary official source:
https://kinkyu.nra.go.jp/

The observer uses only the NRA emergency site. Social media and secondary reporting are not source inputs.

## Runtime paths

```
runtime/jp-nra/
  source/flower.json
  observer/seen.json
  bee/bee_state.json

runtime/jp-nra-core/
  evidence/
  public/public_event.json
```

## Operational deployment

An isolated LIVE deployment has been validated on its own GCP VM with independent failure domain and no dependency on the existing JMA node.

Validated operational properties:
- fail-closed NRA classification policy
- live official-source polling
- independent CORE and Bee runtime
- mTLS between Bee and CORE
- exact Honey-chain continuity across process restart
- systemd persistence for CORE, Bee, and Observer timer
- readiness guard so Observer polls only after Bee reaches `SLEEP`
- real VM reboot recovery
- post-reboot LIVE polling
- CA signing private key absent from the node runtime
- CA signing private key custodied off-node in Google Secret Manager
- no external/X publisher connection

The branch and PR remain candidate/review artifacts. Deployment validation does not merge this branch into `main` and does not alter the immutable JMA v0.1 artifacts.

## Reproducible systemd definitions

The exact operational definitions validated on the deployed node are stored under:

```
ops/systemd/
  hive-jp02-nra-core.service
  hive-jp02-nra-bee.service
  hive-jp02-nra-observer.service
  hive-jp02-nra-observer.timer
  wait_for_bee_ready.sh
```

Captured SHA-256 values:

```
c44683415ff9bf3b67dc652fd216425fcac685c482b33b586b06dce1632bdf39  hive-jp02-nra-bee.service
3d4e43d66b5621eda51243527d132e490c1e4a66efb4973e176aeee40e9419eb  hive-jp02-nra-core.service
d331655b4fa74dc5fba7184718b5ddac7366dd5bd36f19409fd9293ac1d85d0c  hive-jp02-nra-observer.service
8bc1725892cb841895cf4488a0087bcf38d484c63ef834ddda3c24284e40a7c3  hive-jp02-nra-observer.timer
1268b714b5621e509c5bc63fe93bf25894783091ed435dc47c96e0f7e83b9252  wait_for_bee_ready.sh
```

## Status

LIVE isolated deployment validated.
PR remains draft and unmerged.
External/X publication remains disabled.
JMA remains unchanged.
