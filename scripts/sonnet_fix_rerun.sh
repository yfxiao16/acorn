#!/bin/zsh
# After-fix measurement of the three Sonnet x acorn max_steps-cluster cells.
# Waits for the before-fix VC acorn cell to land and for all Sonnet lanes to
# finish, then reruns each cluster cell on an open pool -> *_fix.json.
cd /Users/yifengxiao/Documents/acorn
PY=/opt/homebrew/bin/python3.13; R=results
M="bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0"
while [ ! -f $R/sonnet_video_classification_acorn.json ] || pgrep -f "cells_sonnet" >/dev/null; do sleep 600; done
probe() { AWS_REGION=$1 timeout 90 python3 - <<'PYX' >/dev/null 2>&1
import sys; sys.path.insert(0,'.'); sys.path.insert(0,'../ContrAgent')
from acorn.envfile import load_dotenv; load_dotenv('.env')
from acorn import models
models.resolve('bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0').generate([{"role":"user","content":"reply with exactly: ok"}], [])
PYX
}
for D in video_classification aircraft_inspection warehouse_package_inspection; do
  OUT=$R/sonnet_${D}_acorn_fix.json
  until [ -f $OUT ]; do
    for REG in us-east-2 us-east-1 us-west-2; do
      if probe $REG; then
        echo "$(date '+%m-%d %H:%M') fix-rerun $D on $REG"
        AWS_REGION=$REG $PY benchmarks/amazon_sopbench/run_pack.py \
          --pack benchmarks/amazon_sopbench/data/${D}_sop --model $M --condition acorn --out $OUT 2>&1 | tail -2
        [ -f $OUT ] && break
      fi
    done
    [ -f $OUT ] || sleep 900
  done
done
echo SONNET_FIX_RERUN_DONE
