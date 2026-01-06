# main.py (MicroPython / Raspberry Pi Pico W)
import network, socket, time, math
from machine import Pin
import sys
try:
    import errno
except:
    errno = None

# =========================
# Config
# =========================
AP_SSID = "PICO-TIMER"
AP_PASS = "12345678"   # 8+ chars
LED_PIN = 15           # external LED on GP15
MAX_SECONDS = 3600

POLL_HINT_MS = 400     # (browser side) you can change later
CLIENT_TIMEOUT_S = 2   # socket recv timeout
AP_LOG_EVERY_MS = 5000
AP_ENSURE_EVERY_MS = 5000

# =========================
# Heartbeat (onboard LED)
# =========================
hb = Pin("LED", Pin.OUT)   # Pico W onboard LED
hb.value(0)
_last_hb = time.ticks_ms()

def heartbeat():
    global _last_hb
    now = time.ticks_ms()
    if time.ticks_diff(now, _last_hb) >= 1000:  # 1Hz
        hb.toggle()
        _last_hb = now

# =========================
# Country (important for Wi-Fi stability)
# =========================
try:
    import rp2
    rp2.country("JP")
except Exception as e:
    print("rp2.country not set:", e)

# =========================
# External LED
# =========================
led = Pin(LED_PIN, Pin.OUT)
led.value(0)

# =========================
# Timer state
# =========================
deadline_ms = None
running = False

def set_timer(seconds: int):
    global deadline_ms, running
    if seconds < 1:
        seconds = 1
    if seconds > MAX_SECONDS:
        seconds = MAX_SECONDS
    deadline_ms = time.ticks_add(time.ticks_ms(), seconds * 1000)
    running = True
    led.value(0)

def stop_timer():
    global running
    running = False

def remaining_seconds():
    # display-friendly remaining seconds (ceil)
    if (not running) or (deadline_ms is None):
        return 0
    diff = time.ticks_diff(deadline_ms, time.ticks_ms())
    if diff <= 0:
        return 0
    return math.ceil(diff / 1000)

def update_timer():
    global running
    if running and deadline_ms is not None:
        if time.ticks_diff(deadline_ms, time.ticks_ms()) <= 0:
            running = False
            led.value(1)  # done -> ON

# =========================
# AP setup / keep-alive
# =========================
ap = network.WLAN(network.AP_IF)
_last_ap_log = time.ticks_ms()
_last_ap_ensure = time.ticks_ms()

def start_ap():
    ap.active(False)
    time.sleep(0.2)
    ap.active(True)

    # iPhoneでSSIDが出ないケースがあるので、まずは channel 指定なし（自動）
    ap.config(essid=AP_SSID, password=AP_PASS)

    # wait a bit
    for _ in range(50):
        if ap.active():
            break
        time.sleep(0.1)

    print("AP active:", ap.active(), "status:", ap.status(), "ifconfig:", ap.ifconfig())

def ensure_ap():
    global _last_ap_ensure
    now = time.ticks_ms()
    if time.ticks_diff(now, _last_ap_ensure) < AP_ENSURE_EVERY_MS:
        return
    _last_ap_ensure = now

    if not ap.active():
        print("AP down -> restarting AP")
        start_ap()

def log_ap():
    global _last_ap_log
    now = time.ticks_ms()
    if time.ticks_diff(now, _last_ap_log) >= AP_LOG_EVERY_MS:
        print("AP active:", ap.active(), "status:", ap.status(), "ifconfig:", ap.ifconfig())
        _last_ap_log = now

start_ap()
ip = ap.ifconfig()[0]
print("AP ready:", AP_SSID, "IP:", ip)

# =========================
# HTML
# =========================
HTML = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PICO TIMER</title>
<style>
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:18px}
  .card{max-width:520px;border:1px solid #9996;border-radius:14px;padding:14px}
  input{padding:10px 12px;border-radius:12px;border:1px solid #9996;width:140px;font-weight:800}
  button{padding:10px 14px;border-radius:12px;border:1px solid #9996;background:transparent;font-weight:900}
  .big{font-size:44px;font-weight:1000;margin:10px 0}
  .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
  .hint{opacity:.8;font-size:14px}
</style>
</head>
<body>
<h1>PICO TIMER</h1>
<div class="card">
  <div class="row">
    <input id="sec" type="number" min="1" max="3600" value="10">
    <button onclick="start()">Start</button>
    <button onclick="stopT()">Stop</button>
    <button onclick="off()">LED Off</button>
  </div>
  <div class="big" id="remain">--:--</div>
  <div class="hint">秒で指定（最大3600秒=60分）。例: 1500=25分</div>
</div>

<script>
async function start(){
  const sec = Number(document.getElementById('sec').value || 1);
  await fetch(new URL('/set', location.href), {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: `sec=${encodeURIComponent(sec)}`
  });
}
async function stopT(){ await fetch(new URL('/stop', location.href), { method:'POST' }); }
async function off(){ await fetch(new URL('/ledoff', location.href), { method:'POST' }); }

function fmt(s){
  s = Math.max(0, Math.floor(s));
  const mm = String(Math.floor(s/60)).padStart(2,'0');
  const ss = String(s%60).padStart(2,'0');
  return `${mm}:${ss}`;
}

let polling = false;
let lastShown = null;

async function poll(){
  if (polling) return;      // prevent overlap
  polling = true;

  const remainEl = document.getElementById('remain');
  try{
    const url = new URL('/status', location.href);
    url.searchParams.set('ts', Date.now()); // cache-bust

    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 2000);

    const r = await fetch(url.toString(), { cache: "no-store", signal: ac.signal });
    clearTimeout(t);

    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json();

    lastShown = j.remaining;
    remainEl.textContent = fmt(j.remaining);
    document.title = `⏱ ${fmt(j.remaining)}`;
  }catch(e){
    // don't flash ERR; keep last value if any
    if (lastShown !== null) remainEl.textContent = fmt(lastShown);
    else remainEl.textContent = "--:--";
    console.log("poll error:", e);
  }finally{
    polling = false;
  }
}

setInterval(poll, 900);
poll();
</script>
</body>
</html>
"""

# =========================
# HTTP helpers
# =========================
def http_response(body, content_type="text/html; charset=utf-8", code="200 OK"):
    hdr = (
        "HTTP/1.1 {}\r\n"
        "Content-Type: {}\r\n"
        "Content-Length: {}\r\n"
        "Cache-Control: no-store, no-cache, must-revalidate, max-age=0\r\n"
        "Pragma: no-cache\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).format(code, content_type, len(body))
    return hdr.encode() + body

def header_value(req_bytes, name_bytes):
    try:
        head = req_bytes.split(b"\r\n\r\n", 1)[0]
        for line in head.split(b"\r\n")[1:]:
            if line.lower().startswith(name_bytes.lower() + b":"):
                return line.split(b":", 1)[1].strip()
    except:
        pass
    return None

def parse_form(body_bytes):
    try:
        s = body_bytes.decode()
        kv = {}
        for p in s.split("&"):
            if "=" in p:
                k, v = p.split("=", 1)
                kv[k] = v
        return kv
    except:
        return {}

def safe_errno(e):
    return getattr(e, "errno", None)

def is_timeout_errno(e):
    en = safe_errno(e)
    # MicroPython sometimes reports 110, sometimes ETIMEDOUT constant
    if en == 110:
        return True
    if errno and en == errno.ETIMEDOUT:
        return True
    return False

# =========================
# Server setup
# =========================
addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(addr)
srv.listen(2)           # a bit more breathing room
srv.settimeout(0.2)

print("Open: http://{}/".format(ip))

# =========================
# Main loop (NEVER crash)
# =========================
while True:
    heartbeat()
    update_timer()
    ensure_ap()
    log_ap()

    # accept may timeout: ignore
    try:
        cl, remote = srv.accept()
    except OSError as e:
        if is_timeout_errno(e):
            continue
        # other accept errors: log and continue (do not crash)
        sys.print_exception(e)
        continue

    try:
        cl.settimeout(CLIENT_TIMEOUT_S)

        # recv first chunk
        try:
            req = cl.recv(2048)
        except OSError as e:
            # client disappeared etc.
            sys.print_exception(e)
            continue

        if not req:
            continue

        # parse request line
        try:
            line = req.split(b"\r\n", 1)[0].decode()
            method, path, _ = line.split(" ")
            # remove query string
            path_only = path.split("?", 1)[0]
        except Exception as e:
            sys.print_exception(e)
            cl.send(http_response(b"Bad Request\n", "text/plain", "400 Bad Request"))
            continue

        # ROUTES
        if method == "GET" and path_only == "/":
            cl.send(http_response(HTML.encode()))

        elif method == "GET" and path_only == "/status":
            rem = remaining_seconds()
            body = ('{"running":%s,"remaining":%d,"led":%d}\n' %
                    ("true" if running else "false", rem, led.value())).encode()
            cl.send(http_response(body, "application/json"))

        elif method == "POST" and path_only == "/set":
            # extract header/body
            if b"\r\n\r\n" in req:
                head, body = req.split(b"\r\n\r\n", 1)
            else:
                head, body = req, b""

            clen_b = header_value(req, b"Content-Length")
            try:
                clen = int(clen_b) if clen_b else 0
            except:
                clen = 0

            # read remaining body (do not crash on timeout)
            while len(body) < clen:
                try:
                    more = cl.recv(2048)
                    if not more:
                        break
                    body += more
                except OSError as e:
                    # timeout or client drop: stop reading
                    sys.print_exception(e)
                    break

            kv = parse_form(body)
            try:
                sec = int(kv.get("sec", "1"))
            except:
                sec = 1

            set_timer(sec)
            cl.send(http_response(b"OK\n", "text/plain"))

        elif method == "POST" and path_only == "/stop":
            stop_timer()
            cl.send(http_response(b"OK\n", "text/plain"))

        elif method == "POST" and path_only == "/ledoff":
            led.value(0)
            cl.send(http_response(b"OK\n", "text/plain"))

        else:
            cl.send(http_response(b"Not Found\n", "text/plain", "404 Not Found"))

    except Exception as e:
        # Any unexpected bug: print to REPL but do not crash
        sys.print_exception(e)
        try:
            cl.send(http_response(b"Error\n", "text/plain", "500 Internal Server Error"))
        except:
            pass
    finally:
        try:
            cl.close()
        except:
            pass


