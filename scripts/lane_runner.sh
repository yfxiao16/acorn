#!/bin/zsh
# usage: lane_runner.sh <model-string> <tag> <region> <cells-file>
# cells-file lines: "<domain> <condition> [extra args...]"
PY=/opt/homebrew/bin/python3.13
cd /Users/yifengxiao/Documents/acorn
export AWS_REGION=$3
M=$1; TAG=$2; R=/Users/yifengxiao/Documents/acorn/results
while read -r D C EXTRA; do
  [ -z "$D" ] && continue
  SUF=$(echo "$EXTRA" | sed 's/--flow-profile /prof_/;s/--scaffold /scaf_/;s/ /_/g')
  OUT=$R/${TAG}_${D}_${C}${SUF:+_$SUF}.json
  [ -f $OUT ] && { echo "skip $OUT"; continue }
  if [ -f $OUT.partial.json ] && [ $(( $(date +%s) - $(stat -f %m $OUT.partial.json) )) -lt 1200 ]; then
    echo "skip $OUT (another lane active on it)"; continue
  fi
  touch $OUT.partial.json   # claim the cell now: lanes launched seconds apart otherwise pick the same one
  echo "=== [$TAG@$3] $D $C $EXTRA ==="
  $PY benchmarks/amazon_sopbench/run_pack.py \
    --pack benchmarks/amazon_sopbench/data/${D}_sop \
    --model $M --condition $C ${=EXTRA} --out $OUT 2>&1 | tail -2
done < $4
echo LANE_${TAG}_DONE
