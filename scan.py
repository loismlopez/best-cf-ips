#!/usr/bin/env python3
"""本地直连测速排序：对候选 IP 做 TCP 延迟测速，按延迟排序出 top 文件.

用法：
    python3 scan.py --input candidates_all.txt
    python3 scan.py --input candidates_no104.txt --speed-test 20 --sort speed
    python3 scan.py --input candidates_only104.txt --rounds 4 --workers 50

原理（与 Lancelot 的 scanned 文件同款口径，见 README）：
  1. 每个 IP:port 做 N 轮 TCP connect，取平均延迟 + 丢包率，超时算丢包。
     默认只测延迟，不测下载速度 —— Lancelot 的 top 文件就是“按延迟排序”，
     不是按下载速度排序。想按速度排，加 --speed-test + --sort speed。
  2. 对测通的 IP 再请求 https://IP/cdn-cgi/trace（SNI=www.cloudflare.com），
     从返回的 loc= 取国家码（SG/US/…），colo= 取机房码。不通则国家记 N/A。
  3. 排序：延迟升序，丢包率升序；速度模式下先按速度降序。
  4. 写 result.csv（全量）+ best-cf-ip-scanned-top{20,50,100,200,400}.txt
     （有几个写几个，不足不补空），格式与 Lancelot 一致：
     首行 `# N best cf ips scanned at YYYY-MM-DD HH:MM`，其余 `IP:port#CC 旗`。

注意：
  * 排名只对“跑这台机器的这条线路”有效。VM / GitHub Runner 测出的排名
    不等于你家宽带的排名。本地直连的意思就是：关代理，在你家 WSL/PC 上跑。
  * 平均延迟极低（如 <1ms）说明走了代理，先关代理再测。
  * 并发别太高，HTTPing 本质是扫描行为，并发过高会被运营商/CF 临时限流。
"""
import argparse
import csv
import socket
import ssl
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

FLAGS = {
    "SG": "🇸🇬", "US": "🇺🇸", "HK": "🇭🇰", "JP": "🇯🇵", "KR": "🇰🇷",
    "TW": "🇹🇼", "DE": "🇩🇪", "GB": "🇬🇧", "FR": "🇫🇷", "NL": "🇳🇱",
    "CA": "🇨🇦", "AU": "🇦🇺", "IN": "🇮🇳", "BR": "🇧🇷", "AE": "🇦🇪",
}
TRACE_HOST = "www.cloudflare.com"
SPEED_HOST = "speed.cloudflare.com"


def tcp_latency(ip: str, port: int, rounds: int, timeout: float) -> tuple[float | None, float]:
    lats: list[float] = []
    for _ in range(rounds):
        t0 = time.monotonic()
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                lats.append((time.monotonic() - t0) * 1000)
        except OSError:
            pass
    if not lats:
        return None, 1.0
    return sum(lats) / len(lats), 1 - len(lats) / rounds


def _parse_trace(text: str) -> tuple[str, str]:
    loc = colo = "N/A"
    for line in text.splitlines():
        if line.startswith("loc="):
            loc = line[4:].strip()
        elif line.startswith("colo="):
            colo = line[5:].strip()
    return loc, colo


def trace_country(ip: str, port: int, timeout: float = 5.0) -> tuple[str, str]:
    """返回 (国家码, 机房码)，失败返回 ('N/A', 'N/A')。
    优先用 curl --resolve（能走 CONNECT 代理、SNI 正确），失败再直连 TLS。
    """
    try:
        r = subprocess.run(
            ["curl", "-sk", "--max-time", str(int(timeout)),
             "--resolve", f"{TRACE_HOST}:{port}:{ip}",
             f"https://{TRACE_HOST}/cdn-cgi/trace"],
            capture_output=True, timeout=timeout + 2, check=False)
        if r.returncode == 0 and b"loc=" in r.stdout:
            return _parse_trace(r.stdout.decode(errors="ignore"))
    except Exception:  # noqa: BLE001 - curl 不可用时走直连
        pass
    try:
        ctx = ssl.create_default_context()
        raw = socket.create_connection((ip, port), timeout=timeout)
        with ctx.wrap_socket(raw, server_hostname=TRACE_HOST) as ss:
            ss.sendall(
                f"GET /cdn-cgi/trace HTTP/1.1\r\nHost: {TRACE_HOST}\r\n"
                "User-Agent: cf-scan/1.0\r\nConnection: close\r\n\r\n".encode()
            )
            data = b""
            while True:
                chunk = ss.recv(4096)
                if not chunk:
                    break
                data += chunk
                if len(data) > 8192:
                    break
        return _parse_trace(data.decode(errors="ignore"))
    except Exception:  # noqa: BLE001 - 单 IP trace 失败不杀整批
        return "N/A", "N/A"


def speed_mbps(ip: str, port: int, nbytes: int = 1_000_000, timeout: float = 10.0) -> float:
    """从 speed.cloudflare.com 下 nbytes 字节测速，失败返回 0。优先 curl --resolve。"""
    try:
        r = subprocess.run(
            ["curl", "-sk", "--max-time", str(int(timeout)),
             "--resolve", f"{SPEED_HOST}:{port}:{ip}",
             f"https://{SPEED_HOST}/__down?bytes={nbytes}",
             "-o", "/dev/null", "-w", "%{time_total} %{size_download}"],
            capture_output=True, timeout=timeout + 2, check=False)
        if r.returncode == 0:
            parts = r.stdout.decode().split()
            if len(parts) == 2:
                dt, got = float(parts[0]), float(parts[1])
                if dt > 0 and got > 0:
                    return (got / 1_000_000) / dt
    except Exception:  # noqa: BLE001
        pass
    try:
        ctx = ssl.create_default_context()
        raw = socket.create_connection((ip, port), timeout=timeout)
        with ctx.wrap_socket(raw, server_hostname=SPEED_HOST) as ss:
            ss.settimeout(timeout)
            ss.sendall(
                f"GET /__down?bytes={nbytes} HTTP/1.1\r\nHost: {SPEED_HOST}\r\n"
                "User-Agent: cf-scan/1.0\r\nConnection: close\r\n\r\n".encode()
            )
            t0 = time.monotonic()
            got = 0
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = ss.recv(65536)
                if not chunk:
                    return 0.0
                buf += chunk
            _, body = buf.split(b"\r\n\r\n", 1)
            got += len(body)
            while got < nbytes:
                chunk = ss.recv(65536)
                if not chunk:
                    break
                got += len(chunk)
            dt = time.monotonic() - t0
        return (got / 1_000_000) / dt if dt > 0 else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="candidates_*.txt，每行 IP:port")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--workers", type=int, default=50)
    ap.add_argument("--speed-test", type=int, default=0, help="对延迟前 N 名做下载测速，0=不测")
    ap.add_argument("--sort", choices=["latency", "speed"], default="latency")
    ap.add_argument("--out-suffix", default="", help="如 jp：输出 best-cf-ip-scanned-top20-jp.txt")
    ap.add_argument("--label-country", default="", help="如 JP：top 文件里的 #CC 一律写该国家（按候选池归属标，不用实测落点）；留空则用 trace 实测国家")
    ap.add_argument("--result-file", default="result.csv")
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cands: list[tuple[str, int]] = []
    for line in Path(args.input).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ip, _, port = line.partition(":")
        cands.append((ip, int(port) if port else 443))
    cands = sorted(set(cands))
    print(f"candidates: {len(cands)} from {args.input}")

    def probe(c: tuple[str, int]) -> dict | None:
        ip, port = c
        avg, loss = tcp_latency(ip, port, args.rounds, args.timeout)
        if avg is None:
            return None
        country, colo = trace_country(ip, port)
        return {"ip": ip, "port": port, "loss": loss, "avg_ms": avg,
                "country": country, "colo": colo, "speed": 0.0}

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        rows = [r for r in ex.map(probe, cands) if r]
    print(f"reachable: {len(rows)}/{len(cands)}")
    if rows and min(r["avg_ms"] for r in rows) < 5:
        print("WARNING: 最快 IP 延迟 <5ms，疑似走了代理/出口拦截，"
              "此排名不可用，先关代理再测。")
    rows.sort(key=lambda r: (r["avg_ms"], r["loss"]))

    if args.speed_test > 0:
        top = rows[: args.speed_test]
        with ThreadPoolExecutor(max_workers=5) as ex:
            speeds = list(ex.map(lambda r: speed_mbps(r["ip"], r["port"]), top))
        for r, s in zip(top, speeds):
            r["speed"] = round(s, 2)
        if args.sort == "speed":
            rows = sorted(rows, key=lambda r: (-r["speed"], r["avg_ms"]))

    stamp = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")
    with open(out_dir / args.result_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ip", "port", "loss", "avg_ms", "speed_mbps", "colo", "country"])
        for r in rows:
            w.writerow([r["ip"], r["port"], f"{r['loss']:.2f}", f"{r['avg_ms']:.2f}",
                        f"{r['speed']:.2f}", r["colo"], r["country"]])
    # top 文件只收国家码已确认的：trace 失败的 N/A 不进优选，只留在 result.csv 里备查。
    # 否则 edgetunnel/CFPilot 会拿到 `#N/A` 这种没法按国家分组的节点。
    ranked = [r for r in rows if r["country"] != "N/A"]
    print(f"ranked (country known): {len(ranked)}/{len(rows)}")
    for n in (20, 50, 100, 200, 400):
        take = ranked[:n]
        if not take:
            continue
        speed_note = " (by download speed)" if args.sort == "speed" else ""
        lines = [f"# {len(take)} best cf ips scanned at {stamp}{speed_note}", ""]
        for r in take:
            cc = args.label_country or r["country"]
            flag = FLAGS.get(cc, "")
            lines.append(f"{r['ip']}:{r['port']}#{cc} {flag}".rstrip())
            lines.append("")
        suffix = f"-{args.out_suffix}" if args.out_suffix else ""
        (out_dir / f"best-cf-ip-scanned-top{n}{suffix}.txt").write_text(
            "\n".join(lines), encoding="utf-8")
        print(f"top{n}{suffix}: {len(take)}")
    if rows:
        print(f"best: {rows[0]['ip']}:{rows[0]['port']} {rows[0]['avg_ms']:.2f}ms "
              f"loss={rows[0]['loss']:.2f} {rows[0]['country']}/{rows[0]['colo']}")


if __name__ == "__main__":
    main()
