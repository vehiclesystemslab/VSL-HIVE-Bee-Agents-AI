#!/usr/bin/env bash

BASE="/home/andresborda/hive-jp02-nra"
STATE="$BASE/runtime/jp-nra/bee/bee_state.json"

for i in $(seq 1 50)
do
    if [ -s "$STATE" ] &&
       grep -q "\"state\": \"SLEEP\"" "$STATE"
    then
        echo "BEE_READY_FOR_OBSERVER=PASS"
        exit 0
    fi

    sleep 0.2
done

echo "BEE_NOT_READY_FOR_OBSERVER" >&2
exit 1
