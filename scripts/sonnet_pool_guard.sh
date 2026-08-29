#!/bin/zsh
# Per-region Sonnet pool guard: every 15 min probe each region; if a region
# is capped, kill its runner (garbage otherwise); if open and idle, relaunch
# that region's lane. Exits when the forward list is complete.
cd /Users/yifengxiao/Documents/acorn
S=scripts; R=results
M="bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0"
probe() { AWS_REGION=$1 timeout 90 python3 - <<'PY' >/dev/null 2>&1
import sys; sys.path.insert(0,'.'); sys.path.insert(0,'../ContrAgent')
from acorn.envfile import load_dotenv; load_dotenv('.env')
from acorn import models
models.resolve('bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0').generate([{"role":"user","content":"reply with exactly: ok"}], [])
PY
}
runner_in() { for p in $(pgrep -f 'run_pack.py.*sonnet'); do ps -E -o command= -p $p | grep -q "AWS_REGION=$1" && echo $p; done }
lane_in() { pgrep -f "lane_runner.sh.*sonnet $1" ; }
while true; do
  left=$(python3 scripts/sonnet_missing.py)
  [ "$left" = "0" ] && { echo "$(date '+%m-%d %H:%M') all sonnet cells present"; break; }
  for REG in us-east-1 us-west-2 us-east-2; do
    LIST=$R/cells_sonnet.txt
    [ $REG = us-west-2 ] && LIST=$R/cells_sonnet_rev.txt
    [ $REG = us-east-2 ] && LIST=$R/cells_sonnet_mid.txt
    if probe $REG; then
      if [ -z "$(lane_in $REG)" ]; then
        echo "$(date '+%m-%d %H:%M') $REG open + idle -> launch"
        $S/lane_runner.sh "$M" sonnet $REG $LIST >> $R/lane_sonnet_guard_$REG.log 2>&1 &
      fi
    else
      for p in $(runner_in $REG); do echo "$(date '+%m-%d %H:%M') $REG capped -> kill runner $p"; kill -9 $p; done
      pkill -f "lane_runner.sh.*sonnet $REG" 2>/dev/null
    fi
  done
  sleep 900
done
echo SONNET_POOL_GUARD_DONE
