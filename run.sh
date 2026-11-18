#!/usr/bin/env bash
# 本地一键跑：收集 -> 直连测速 -> 出 top 文件
# 在你家 WSL 里跑，关代理再跑。FILTER 改下面一行：
#   all=全部（默认） no104=去掉 104.*  only104=只留 104.*
set -euo pipefail
cd "$(dirname "$0")"
FILTER="${FILTER:-all}"

python3 collect.py
case "$FILTER" in
  no104)   INPUT=candidates_no104.txt ;;
  only104) INPUT=candidates_only104.txt ;;
  *)       INPUT=candidates_all.txt ;;
esac
echo "scan input: $INPUT"
python3 scan.py --input "$INPUT"
echo "--- top20 ---"
head -n 12 best-cf-ip-scanned-top20.txt 2>/dev/null || head -n 12 result.csv
