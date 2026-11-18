#!/usr/bin/env bash
# 本地自动跑（在你家 WSL 里，关代理再跑）：收集 -> 直连测延迟+下载速度 -> 地区文件 -> 合并 -> 提交推送
# 用法：./run_local.sh
# 定时：Windows 任务计划程序每 6 小时跑一次，或 WSL cron，见 README 的“本地自动运行”一节。
# 注意：先 git pull --rebase 再 push，避免远程 workflow 提交导致的 push 被拒。
set -euo pipefail
cd "$(dirname "$0")"
# 强制直连：清掉代理环境变量，否则测速会走代理、延迟假低、trace 全 N/A
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY || true
export FILTER="${FILTER:-no104}"

echo "=== pull ==="
git pull --rebase -X theirs || true

echo "=== collect ==="
python3 collect.py

echo "=== scan (latency + download speed, sort by speed) ==="
python3 scan.py --input candidates_no104.txt --speed-test 20 --sort speed

echo "=== regions ==="
python3 build_region.py --region jp
python3 build_region.py --region us
python3 build_region.py --region sg
python3 merge_regions.py

echo "=== commit + push ==="
git add best-cf-ip-scanned-top*.txt result.csv result-jp.csv result-us.csv result-sg.csv candidates_*.txt
git diff --cached --quiet && echo "no change" || git commit -m "top cf ips updated $(date -u +'%Y-%m-%d %H:%M') [skip ci]"
git push
echo "=== done ==="
head -n 4 best-cf-ip-scanned-top-region.txt
