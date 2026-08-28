#!/bin/zsh
PY=/opt/homebrew/bin/python3.13
R=/Users/yifengxiao/Documents/acorn/results
S=/Users/yifengxiao/Documents/acorn/scripts
busy() {
  for p in $(pgrep -f "run_pack.py"); do
    c=$(ps -o comm= -p $p 2>/dev/null)
    case $c in *zsh*|*bash*|"") ;; *) return 0 ;; esac
  done
  return 1
}
for ROUND in 1 2 3; do
  while busy; do sleep 600; done
  sleep 60
  N=$($PY - <<'PYEOF'
import json, glob, os
n=0
for f in glob.glob('/Users/yifengxiao/Documents/acorn/results/*.json'):
    try:
        d=json.load(open(f))
        errs=sum(1 for r in d.get('rows',[]) if r.get('status')=='error')
        rows=d.get('rows',[]); nosub=sum(1 for r in rows if r.get('got') is None and r.get('status')=='max_steps')
        if errs>3:  # max_steps clusters are a real Sonnet x acorn finding, not damage -- never auto-delete
            print('DEL', os.path.basename(f), 'err', errs, 'nosub', nosub); os.remove(f); n+=1
    except Exception: os.remove(f); n+=1
print(n)
PYEOF
)
  echo "round $ROUND: $N"
  [ "$(echo $N | tail -1)" = "0" ] && break
  $S/lane_runner.sh "bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0" haiku us-east-1 $R/cells_haiku_full.txt &
  $S/lane_runner.sh "bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0" sonnet us-west-2 $R/cells_sonnet.txt &
  $S/lane_runner.sh "bedrock:openai.gpt-oss-120b-1:0" oss us-west-2 $R/cells_oss.txt &
  $S/lane_runner.sh "bedrock:us.meta.llama3-3-70b-instruct-v1:0" llama us-west-2 $R/cells_llama.txt &
  wait
done
echo SCAN_REBUILD_CLEAN
