#!/usr/bin/env python3
"""从 Cloudflare 官方 IPv4 段扩池：每 /24 取 1 个 IP，排除 104.*。

为什么需要它：
  现有 12 个源都是别人筛好的优选列表（每份 3–37 条），原始 190 行、
  去重后 173 条，排除 104 后 144 条，凑不满 top100/400。
  Cloudflare 官方段（https://www.cloudflare.com/ips-v4）共 15 段、
  1,524,736 个 IP、5,956 个 /24，排除 104.16.0.0/13 + 104.24.0.0/14
  后剩 2,884 个 /24，即 2,884 个候选。

用法：
    python3 expand_cidr.py [--out-dir .] [--host 1]
输出：candidates_cidr.txt（每行 `IP:443`，按段顺序，已排除 104.*）
注意：
  * 只扩全局池（scan.py 的 Runner 实测文件），不扩 JP/US/SG 地区文件——
    地区文件是“从中国看”的源站顺序，CIDR 采样不知道它从中国落哪里。
  * 2,884 条全测比 144 条慢得多，workflow 的 timeout 30 分钟要留够；
    接入 workflow 前先在本地 / 手动跑一次看耗时。
  * .1 是每 /24 的确定性代表地址（不随机，保证每次跑出同一批）。
"""
import argparse
import ipaddress
import urllib.request
from pathlib import Path

CF_IPS_V4 = "https://www.cloudflare.com/ips-v4"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--host", type=int, default=1, help="/24 内取第几个主机地址，默认 .1")
    args = ap.parse_args()
    req = urllib.request.Request(CF_IPS_V4, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        text = r.read().decode("utf-8", errors="ignore")
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        net = ipaddress.ip_network(line)
        if str(net.network_address).startswith("104."):
            continue
        for sub in net.subnets(new_prefix=24):
            out.append(f"{sub.network_address + args.host}:443")
    p = Path(args.out_dir) / "candidates_cidr.txt"
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"candidates_cidr.txt: {len(out)}")


if __name__ == "__main__":
    main()
