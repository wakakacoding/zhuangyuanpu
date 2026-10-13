#!/bin/zsh
# 构建辅助脚本：始终在 site 目录执行，避免 cwd 问题
cd "$(dirname "$0")" || exit 1
NODE=/Users/mba/.workbuddy/binaries/node/versions/22.22.2-6/bin/node
time ($NODE node_modules/.bin/astro build 2>&1 | grep -vE "safe-delete|removeEmptyDirs|Stack trace|at " | tail -3)
echo "人物页数: $(ls dist/persons | wc -l | tr -d ' ')"
echo "产物体积: $(du -sh dist | cut -f1)"
