#!/bin/sh
# FEAT-181: the economy ledger is shared between services as byte-identical
# copies (no shared package). This guard fails CI when any copy drifts.
# Usage: sh scripts/check_econ_copies.sh   (from any directory)
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

FAILED=0

# check_group <label> <reference file> <copy>...
# Every copy must have the same sha256 as the reference (the first file).
check_group() {
    label=$1
    shift
    ref=$1
    if [ ! -f "$ref" ]; then
        echo "ERROR [$label]: reference file is missing: $ref" >&2
        FAILED=1
        return
    fi
    ref_sum=$(sha256sum "$ref" | cut -d ' ' -f 1)
    shift
    for copy in "$@"; do
        if [ ! -f "$copy" ]; then
            echo "ERROR [$label]: copy is missing: $copy" >&2
            FAILED=1
            continue
        fi
        sum=$(sha256sum "$copy" | cut -d ' ' -f 1)
        if [ "$sum" != "$ref_sum" ]; then
            echo "ERROR [$label]: $copy differs from $ref" >&2
            echo "    $ref_sum  $ref" >&2
            echo "    $sum  $copy" >&2
            FAILED=1
        else
            echo "ok   [$label]: $copy"
        fi
    done
}

check_group "econ_core" \
    services/character-service/app/econ_core.py \
    services/inventory-service/app/econ_core.py \
    services/locations-service/app/econ_core.py \
    services/dungeon-service/app/econ_core.py

check_group "econ_contract_cases" \
    services/character-service/app/tests/econ_contract_cases.py \
    services/inventory-service/app/tests/econ_contract_cases.py \
    services/locations-service/app/tests/econ_contract_cases.py \
    services/dungeon-service/app/tests/econ_contract_cases.py

check_group "econ_ledger (sync)" \
    services/character-service/app/econ_ledger.py \
    services/inventory-service/app/econ_ledger.py

check_group "econ_ledger (async)" \
    services/locations-service/app/econ_ledger.py \
    services/dungeon-service/app/econ_ledger.py

if [ "$FAILED" -ne 0 ]; then
    echo "Economy ledger copies are out of sync. Edit the canonical file" >&2
    echo "(character-service for core/cases/sync ledger, locations-service" >&2
    echo "for the async ledger) and copy it byte-for-byte to the others." >&2
    exit 1
fi
echo "All economy ledger copies are identical."
