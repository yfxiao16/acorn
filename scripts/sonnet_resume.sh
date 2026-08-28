#!/bin/zsh
# Wait for the Bedrock daily token-quota reset (UTC midnight), then relaunch both Sonnet lanes.
S=/Users/yifengxiao/Documents/acorn/scripts; R=/Users/yifengxiao/Documents/acorn/results
now=$(date -u +%s); reset=$(date -u -v+1d -v0H -v15M -v0S +%s)
echo "sleeping $(( (reset-now)/60 )) min until UTC 00:15"; sleep $(( reset-now ))
$S/lane_runner.sh "bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0" sonnet us-east-1 $R/cells_sonnet.txt > $R/lane_sonnet_east2.log 2>&1 &
$S/lane_runner.sh "bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0" sonnet us-west-2 $R/cells_sonnet_rev.txt > $R/lane_sonnet_rev2.log 2>&1 &
wait; echo SONNET_RESUME_DONE
