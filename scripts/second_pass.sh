#!/bin/zsh
# Re-run each lane list once more after the current pass drains, so cells
# lost to earlier watchdog false-kills get rebuilt (guards skip completed).
S=/Users/yifengxiao/Documents/acorn/scripts
R=/Users/yifengxiao/Documents/acorn/results
busy() {
  for p in $(pgrep -f "run_pack.py"); do
    c=$(ps -o comm= -p $p 2>/dev/null)
    case $c in *zsh*|*bash*|"") ;; *) return 0 ;; esac
  done
  return 1
}
while busy; do sleep 300; done
sleep 30
$S/lane_runner.sh "bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0" haiku us-west-2 $R/cells_react.txt &
$S/lane_runner.sh "bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0" haiku us-east-1 $R/cells_haiku_full.txt &
$S/lane_runner.sh "bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0" sonnet us-east-1 $R/cells_sonnet.txt &
$S/lane_runner.sh "bedrock:openai.gpt-oss-120b-1:0" oss us-west-2 $R/cells_oss.txt &
$S/lane_runner.sh "bedrock:us.meta.llama3-3-70b-instruct-v1:0" llama us-west-2 $R/cells_llama.txt &
wait
echo SECOND_PASS_DONE
