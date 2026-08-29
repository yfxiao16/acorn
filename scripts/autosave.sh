#!/bin/zsh
cd /Users/yifengxiao/Documents/acorn
while true; do
  sleep 3600
  git add results/ 2>/dev/null
  git diff --cached --quiet || git commit -q -m "autosave: experiment results $(date '+%m-%d %H:%M')" 2>/dev/null
done
