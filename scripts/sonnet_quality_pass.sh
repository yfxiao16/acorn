#!/bin/zsh
# Single-shot: once no Sonnet lane/runner remains, drop Sonnet cells with
# >3 error rows and rerun the forward list once (file guards skip clean cells).
S=/Users/yifengxiao/Documents/acorn/scripts; R=/Users/yifengxiao/Documents/acorn/results
PY=/opt/homebrew/bin/python3.13
while pgrep -f "cells_sonnet" >/dev/null || pgrep -f "sonnet_final.sh" >/dev/null; do sleep 300; done
cd $R && $PY - <<'PYEOF'
import json, glob, os
for f in glob.glob('sonnet_*.json'):
    d=json.load(open(f)); e=sum(1 for r in d['rows'] if r.get('status')=='error')
    if e>3: print('DEL', f, e); os.remove(f)
PYEOF
$S/lane_runner.sh "bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0" sonnet us-east-1 $R/cells_sonnet.txt
echo SONNET_QUALITY_PASS_DONE
