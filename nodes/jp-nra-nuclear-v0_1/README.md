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

## Status

Candidate implementation only.
Not deployed.
Not connected to the existing public X publisher.
