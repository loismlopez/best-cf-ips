#!/usr/bin/env python3
"""建地区文件：从中国看最快的 JP / US / SG —— 不用 Runner 延迟重排.

为什么不用 scan.py 测地区：
  Runner 在美国，到美国边缘只要 6ms，到日本/新加坡要 140–200ms，
  按 Runner 延迟一排，美国永远在前，日本/新加坡永远沉底。
  同一 IP 从中国电信测落 JP/SG，从美国 Runner 测落 US，
  所以 Runner 的延迟排不出“从中国看最快的日本/美国/新加坡”。

本文件的做法（诚实口径）：直接用中国源站自己测好的顺序，不重测。
  1. gslege/<REGION>.txt 的文件顺序（源站按中国实测排好的）
  2. tiancheng/<region>.txt 的文件顺序
  3. junzhen 两文件里标该地区的行，按 [高速 by Jz XXM] 的 M 数降序
  4. love-ztm 里标该地区的行
  去重时保留第一次出现的位置。输出 #JP 🇯🇵 / #US 🇺🇸 / #SG 🇸🇬，
  不写 Runner 测出的 US。result-<region>.csv 留 source + speed 备查。

用法：
    python3 build_region.py --region jp
    python3 build_region.py --region us
    python3 build_region.py --region sg
输出：best-cf-ip-scanned-top20-<region>.txt / top50-<region>.txt / top100-<region>.txt
"""
import argparse
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

IP_PORT_RE = re.compile(r"\b((?:\d{1,3}\.){3}\d{1,3})(?::(\d{1,5}))?")
SPEED_RE = re.compile(r"(\d+(?:\.\d+)?)\s*M\b")
FLAGS = {"JP": "🇯🇵", "US": "🇺🇸", "SG": "🇸🇬"}


def valid_ip(s: str) -> bool:
    try:
        return all(0 <= int(o) <= 255 for o in s.split("."))
    except ValueError:
        return False


def fetch(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def ordered_ips(text: str, skip_header: bool = False) -> list[tuple[str, int, str]]:
    """按文件顺序提 IP。skip_header 跳过首行标题行（162.159.198.1 那行，
    在每个地区文件里都一样，不是该地区最快的）和含“分享免费优选网”的尾行。"""
    out: list[tuple[str, int, str]] = []
    seen: set[tuple[str, int]] = set()
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    if skip_header and lines:
        lines = lines[1:]
    for line in lines:
        if "分享免费优选网" in line:
            continue
        for m in IP_PORT_RE.finditer(line):
            ip, port = m.group(1), m.group(2)
            if not valid_ip(ip):
                continue
            if ip.startswith("104."):
                continue
            p = int(port) if port else 443
            if 1 <= p <= 65535 and (ip, p) not in seen:
                seen.add((ip, p))
                out.append((ip, p, line))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True, choices=["jp", "us", "sg"])
    ap.add_argument("--out-dir", default=".")
    args = ap.parse_args()
    region = args.region.lower()
    REGION = region.upper()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ordered: list[tuple[str, int, str, str]] = []
    seen: set[tuple[str, int]] = set()

    def add(items: list[tuple[str, int, str]], source: str) -> None:
        for ip, port, line in items:
            if (ip, port) in seen:
                continue
            seen.add((ip, port))
            note = ""
            m = SPEED_RE.search(line)
            if m:
                note = f"{m.group(1)}M by {source}"
            ordered.append((ip, port, source, note))

    for url, name in [
        (f"https://bestcf.pages.dev/gslege/{REGION}.txt", f"gslege/{REGION}"),
        (f"https://bestcf.pages.dev/tiancheng/{region}.txt", f"tiancheng/{region}"),
        (f"https://bestcf.pages.dev/s5gy/{region}.txt", f"s5gy/{region}"),
        (f"https://bestcf.pages.dev/tiancheng2/{region}.txt", f"tiancheng2/{region}"),
        (f"https://bestcf.pages.dev/tiancheng3/{region}.txt", f"tiancheng3/{region}"),
    ]:
        try:
            add(ordered_ips(fetch(url), skip_header=True), name)
            print(f"OK {url}")
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {url}: {e}")

    jz: list[tuple[str, int, str, float]] = []
    for url, name in [
        ("https://cf.junzhen.qzz.io/best_ips_bj.txt", "junzhen-bj"),
        ("https://cf.junzhen.qzz.io/best_ips.txt", "junzhen"),
    ]:
        try:
            text = fetch(url)
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {url}: {e}")
            continue
        for line in text.splitlines():
            if REGION not in line:
                continue
            for ip, port, raw in ordered_ips(line):
                m = SPEED_RE.search(raw)
                jz.append((ip, port, name, float(m.group(1)) if m else 0.0))
    jz.sort(key=lambda x: -x[3])
    for ip, port, name, speed in jz:
        if (ip, port) in seen:
            continue
        seen.add((ip, port))
        ordered.append((ip, port, name, f"{speed:g}M by {name}"))

    try:
        text = fetch("https://raw.githubusercontent.com/love-ztm/cfip/refs/heads/main/best_ips.txt")
        add(ordered_ips("\n".join(l for l in text.splitlines() if REGION in l)), "love-ztm")
    except Exception as e:  # noqa: BLE001
        print(f"FAIL love-ztm: {e}")

    print(f"{region} total: {len(ordered)}")
    stamp = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")
    with open(out_dir / f"result-{region}.csv", "w", encoding="utf-8") as f:
        f.write("ip,port,source,note\n")
        for ip, port, source, note in ordered:
            f.write(f"{ip},{port},{source},{note}\n")
    for n in (20, 50, 100):
        take = ordered[:n]
        if not take:
            continue
        lines = [f"# {len(take)} best cf ips scanned at {stamp} ({REGION}, China-measured order)", ""]
        for ip, port, _source, _note in take:
            lines.append(f"{ip}:{port}#{REGION} {FLAGS[REGION]}")
            lines.append("")
        (out_dir / f"best-cf-ip-scanned-top{n}-{region}.txt").write_text("\n".join(lines), encoding="utf-8")
        print(f"top{n}-{region}: {len(take)}")
    if ordered:
        print(f"best {REGION}: {ordered[0][0]}:{ordered[0][1]} from {ordered[0][2]}")


if __name__ == "__main__":
    main()
