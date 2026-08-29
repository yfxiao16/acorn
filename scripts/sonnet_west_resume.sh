#!/bin/zsh
# Probe the west-2 Sonnet pool every 30 min; relaunch the reverse lane once it answers.
cd /Users/yifengxiao/Documents/acorn
S=scripts; R=results
while true; do
  if AWS_REGION=us-west-2 timeout 90 python3 - <<'PY' 2>/dev/null
import sys; sys.path.insert(0,'.'); sys.path.insert(0,'../ContrAgent')
from acorn.envfile import load_dotenv; load_dotenv('.env')
from acorn import models
m = models.resolve('bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0')
m.generate([{"role":"user","content":"reply with exactly: ok"}], [])
PY
  then echo "$(date '+%m-%d %H:%M') west-2 open, launching"; break; fi
  sleep 1800
done
$S/lane_runner.sh "bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0" sonnet us-west-2 $R/cells_sonnet_rev.txt
echo SONNET_WEST_RESUME_DONE
