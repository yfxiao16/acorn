#!/bin/zsh
# After both Sonnet lanes exit, run the forward list once more to pick up
# any cell lost to a watchdog kill (file guards skip completed cells).
S=/Users/yifengxiao/Documents/acorn/scripts; R=/Users/yifengxiao/Documents/acorn/results
while pgrep -f "cells_sonnet" >/dev/null; do sleep 300; done
$S/lane_runner.sh "bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0" sonnet us-east-1 $R/cells_sonnet.txt
echo SONNET_FINAL_DONE
