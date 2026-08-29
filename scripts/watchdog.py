"""Kill run_pack processes that are genuinely stuck (no CPU progress).

Keyed on (pid, process start time): macOS recycles PIDs, and a fresh
process inheriting a recycled PID's stale history was being killed
instantly by the previous pid-only version. A CPU-time decrease also
resets the entry.
"""
import subprocess, time

def sh(*a):
    try: return subprocess.check_output(list(a)).decode()
    except Exception: return ''

def _hms(t):
    s = 0.0
    for x in t.replace('-', ':').split(':'):
        s = s * 60 + float(x)
    return s

hist = {}
STALL_LIMIT = 2400      # 40 min with no CPU progress
AGE_LIMIT = 86400       # 24 h: Sonnet max_steps-cluster cells legitimately run >12 h

while True:
    now = time.time()
    for p in sh('pgrep', '-f', 'run_pack.py').split():
        comm = sh('ps', '-o', 'comm=', '-p', p).strip()
        if not comm or 'zsh' in comm or 'bash' in comm:
            continue
        cput = sh('ps', '-o', 'cputime=', '-p', p).strip()
        start = sh('ps', '-o', 'lstart=', '-p', p).strip()
        etime = sh('ps', '-o', 'etime=', '-p', p).strip()
        if not cput or not start:
            continue
        key = (p, start)                       # identity survives PID reuse
        c = _hms(cput)
        age = _hms(etime) if etime else 0
        last_c, last_t = hist.get(key, (None, now))
        if last_c is None or c > last_c + 0.05 or c < last_c:
            hist[key] = (c, now)
        stall = now - hist[key][1]
        if stall > STALL_LIMIT or age > AGE_LIMIT:
            print(time.strftime('%H:%M'), 'KILL', p, 'stall=%.0f age=%.0f cpu=%.1f' % (stall, age, c), flush=True)
            sh('kill', '-9', p)
            hist.pop(key, None)
    for k in [k for k in hist if now - hist[k][1] > 86400]:
        hist.pop(k, None)
    time.sleep(300)
