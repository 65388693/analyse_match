"""Local web interface for the football match analysis project."""

from datetime import datetime
import base64
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from config import IS_PRODUCTION, WEB_AUTH_PASSWORD, WEB_AUTH_USERNAME
from interactive import load_leagues
from main import analyze_match_cached, analyze_match_data
from match_catalog import build_match_catalog
from live_football_client import get_cached_matches_for_date, get_matches_for_date
from team_history import get_cached_team_full


ROOT = Path(__file__).parent
WEB_DIR = ROOT / "web"
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8765"))


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items() if not str(key).startswith("_")}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _valid_date(value):
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


class MatchDeskHandler(BaseHTTPRequestHandler):
    def _authorized(self, path=""):
        if path == "/health":
            return True
        if not IS_PRODUCTION:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False
        username, separator, password = decoded.partition(":")
        return bool(
            separator
            and hmac.compare_digest(username, WEB_AUTH_USERNAME)
            and hmac.compare_digest(password, WEB_AUTH_PASSWORD)
        )

    def _send(self, status, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(_json_safe(body), ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        request = urlparse(self.path)
        if request.path == "/health":
            return self._send(200, {"status": "ok"})
        if not self._authorized(request.path):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="MatchScope", charset="UTF-8"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if request.path in ("/", "/matchscope-football"):
            return self._send_file("index.html")
        if request.path in ("/app.js", "/styles.css"):
            return self._send_file(request.path.lstrip("/"))
        if request.path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        if request.path == "/api/matches":
            return self._get_matches(parse_qs(request.query))
        self._send(404, {"error": "Route inconnue"})

    def do_POST(self):
        if not self._authorized(urlparse(self.path).path):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="MatchScope", charset="UTF-8"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        route = urlparse(self.path).path
        if route not in ("/api/analyze", "/api/analyze-cached"):
            return self._send(404, {"error": "Route inconnue"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 16_384:
                return self._send(400, {"error": "Requête invalide"})
            payload = json.loads(self.rfile.read(length))
            if route == "/api/analyze-cached":
                self._analyze_cached(payload)
            else:
                self._analyze(payload)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            self._send(400, {"error": f"Requête invalide : {exc}"})

    def _send_file(self, name):
        path = WEB_DIR / name
        if not path.is_file():
            return self._send(404, {"error": "Fichier introuvable"})
        content_type = "text/html; charset=utf-8" if name.endswith(".html") else (
            "text/css; charset=utf-8" if name.endswith(".css") else "text/javascript; charset=utf-8"
        )
        self._send(200, path.read_bytes(), content_type)

    def _get_matches(self, query):
        date = query.get("date", [datetime.now().date().isoformat()])[0]
        if not _valid_date(date):
            return self._send(400, {"error": "Date attendue au format AAAA-MM-JJ"})
        try:
            force_refresh = query.get("refresh", ["0"])[0] == "1"
            events = get_matches_for_date(date, force_refresh=force_refresh)
            if events is None:
                return self._send(502, {"error": "Calendrier indisponible auprès du fournisseur"})
            matches = build_match_catalog(events, date, load_leagues())
            for match in matches:
                league_key = match.get("analysis_league_key")
                match["cache_ready"] = bool(
                    league_key
                    and get_cached_team_full(league_key, match["home_team"])
                    and get_cached_team_full(league_key, match["away_team"])
                )
            self._send(200, {
                "date": date,
                "count": len(matches),
                "coverage": {
                    "analyzable": sum(bool(match.get("analysis_league_key")) for match in matches),
                    "cache_ready": sum(bool(match.get("cache_ready")) for match in matches),
                    "unmapped": sum(not match.get("analysis_league_key") for match in matches),
                },
                "matches": matches,
            })
        except Exception as exc:
            self._send(502, {"error": str(exc)})

    def _analyze(self, payload):
        date = payload.get("date")
        match_id = str(payload.get("match_id") or "")
        if not _valid_date(date) or not match_id:
            return self._send(400, {"error": "Date et identifiant de match requis"})

        events = get_matches_for_date(date)
        if events is None:
            return self._send(502, {"error": "Calendrier indisponible auprès du fournisseur"})
        match = next(
            (item for item in build_match_catalog(events, date, load_leagues())
             if str(item.get("source_match_id")) == match_id),
            None,
        )
        if match is None:
            return self._send(404, {"error": "Match non trouvé pour cette date"})
        league_key = match.get("analysis_league_key")
        if not league_key:
            return self._send(409, {"error": "Cette compétition n'est pas reliée aux statistiques du modèle"})
        try:
            result = analyze_match_data(league_key, match)
            self._send(200, result)
        except ValueError as exc:
            self._send(422, {"error": str(exc)})
        except Exception as exc:
            self._send(502, {"error": f"L'analyse a échoué : {exc}"})

    def _analyze_cached(self, payload):
        date = payload.get("date")
        if not _valid_date(date):
            return self._send(400, {"error": "Date attendue au format AAAA-MM-JJ"})
        events = get_cached_matches_for_date(date)
        if events is None:
            return self._send(502, {"error": "Calendrier absent du cache local"})
        matches = build_match_catalog(events, date, load_leagues())
        results = []
        for match in matches:
            league_key = match.get("analysis_league_key")
            if not league_key:
                continue
            result = analyze_match_cached(league_key, match)
            if result is not None:
                results.append(result)
        self._send(200, {
            "date": date,
            "matches_in_calendar": len(matches),
            "analyzed": len(results),
            "skipped": len(matches) - len(results),
            "additional_api_requests": 0,
            "results": results,
        })

    def log_message(self, format_string, *args):
        print(f"[{self.log_date_time_string()}] {format_string % args}")


def serve():
    server = ThreadingHTTPServer((HOST, PORT), MatchDeskHandler)
    print(f"Match Desk ouvert sur http://{HOST}:{PORT}")
    print("Arrêt : Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nFermeture du serveur.")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()