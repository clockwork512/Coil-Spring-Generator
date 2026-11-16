"""Start the Coil Spring Designer website.

    python run_web.py              # open to your network (coworkers can connect)
    python run_web.py --local      # only this computer
    python run_web.py --port 8080  # use another port

Leave this window open while people use the site; close it (or Ctrl+C) to stop.
"""
import argparse
import socket
import threading
import webbrowser


def lan_addresses():
    """Best guess at this computer's network addresses (no traffic is sent)."""
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def main():
    ap = argparse.ArgumentParser(description="Coil Spring Designer website")
    ap.add_argument("--local", action="store_true", help="only allow this computer to connect")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    a = ap.parse_args()

    import uvicorn
    from coilspring.web.server import app, WEB_VERSION

    host = "127.0.0.1" if a.local else "0.0.0.0"
    # Is something (usually an older copy of this site) already using the port?
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, a.port))
    except OSError:
        print(f"\n  Port {a.port} is already in use - most likely an older copy of the site is still")
        print("  running in another window. Close that window (or restart the computer), then")
        print(f"  start this again. Or use another port:  run_web_windows.bat --port {a.port + 1}\n")
        raise SystemExit(1)
    finally:
        probe.close()
    print(f"\n  Coil Spring Designer website  v{WEB_VERSION}")
    print("  ---------------------------------")
    print(f"  On this computer:   http://localhost:{a.port}")
    if not a.local:
        name = socket.gethostname()
        print(f"  For coworkers:      http://{name}:{a.port}")
        for ip in lan_addresses():
            print(f"                      http://{ip}:{a.port}")
        print("\n  If Windows Firewall asks, allow access on Private networks.")
    print("  Leave this window open while people use the site. Press Ctrl+C to stop.\n")

    if not a.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{a.port}")).start()
    uvicorn.run(app, host=host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
