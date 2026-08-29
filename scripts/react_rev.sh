#!/bin/zsh
S=/Users/yifengxiao/Documents/acorn/scripts; R=/Users/yifengxiao/Documents/acorn/results
while pgrep -f "cells_haiku_full.txt" >/dev/null; do sleep 300; done
$S/lane_runner.sh "bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0" haiku us-east-1 $R/cells_react_rev.txt
