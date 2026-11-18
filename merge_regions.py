#!/usr/bin/env python3
"""把 JP / US / SG 三个地区文件合并成一个。

用法：
    python3 merge_regions.py [--out-dir .]

输入：result-jp.csv、result-us.csv、result-sg.csv（build_region.py 产出，
      已是“从中国看”的顺序、已排除 104.*）
输出：best-cf-ip-scanned-top-region.txt
      结构：总标题 + # JP (n) + 条目 + # US (n) + 条目 + # SG (n) + 条目
      每条仍是 `IP:port#CC 旗`，分节标题行以 # 开头，订阅端按行解析时可跳过。
"""
import argparse
import csv
from datetime import datetime, timezone, timedelta
from pathlib import Path

FLAGS = {"JP": "🇯🇵", "US": "🇺🇸", "SG": "🇸🇬"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=".")
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    sections: list[tuple[str, list[tuple[str, str]]]] = []
    total = 0
    for region in ("jp", "us", "sg"):
        path = out_dir / f"result-{region}.csv"
        items: list[tuple[str, str]] = []
        if not path.exists():
            print(f"skip {region}: {path} 不存在")
            continue
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ip, port = row["ip"], row["port"]
                if ip.startswith("104."):
                    continue
                items.append((ip, port))
        sections.append((region.upper(), items))
        total += len(items)
        print(f"{region}: {len(items)}")
    stamp = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")
    lines = [f"# {total} best cf ips scanned at {stamp} (JP/US/SG, China-measured order)", ""]
    for region, items in sections:
        lines.append(f"# {region} ({len(items)})")
        lines.append("")
        for ip, port in items:
            lines.append(f"{ip}:{port}#{region} {FLAGS[region]}")
            lines.append("")
    (out_dir / "best-cf-ip-scanned-top-region.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"merged: {total} -> best-cf-ip-scanned-top-region.txt")


if __name__ == "__main__":
    main()
