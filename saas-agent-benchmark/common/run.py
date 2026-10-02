"""Run one application: python -m common.run <app_id> [--port N] [--host H]"""
import argparse
import importlib

ap = argparse.ArgumentParser()
ap.add_argument("app")
ap.add_argument("--port", type=int)
ap.add_argument("--host", default="127.0.0.1")
a = ap.parse_args()
app = importlib.import_module(f"apps.{a.app}.app").app
srv = app.serve(a.port, a.host)
print(f"{app.name} listening on http://{a.host}:{srv.server_address[1]}", flush=True)
try:
    srv.serve_forever()
except KeyboardInterrupt:
    pass
