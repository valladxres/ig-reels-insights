#!/usr/bin/env python3
"""CLI para bajar media, comentarios e insights de tus reels de Instagram
via la Graph API oficial de Meta. Solo libreria estandar (sin pip install).

Comandos:
  list                       ultimos reels de la cuenta
  comments <media_id>        comentarios + replies de un reel
  insights <media_id>        metricas de un reel
  bundle <ids...|--recent N> media + insights + comentarios tagueados a JSON
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

DEFAULT_TRIGGERS = [
    "info", "precio", "quiero", "me interesa", "curso", "plantilla",
    "guia", "guía", "ebook", "clases", "mentoria", "mentoría",
]

RETRYABLE_ERROR_CODES = {4, 17, 32, 613, 80004, 429}
TOKEN_ENV_VAR = "INSTAGRAM_ACCESS_TOKEN"


class GraphAPIError(RuntimeError):
    pass


def load_env(env_path: Path) -> None:
    """Carga variables tipo KEY=VALUE del .env indicado, sin pisar las que
    ya existan en el entorno del proceso."""
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def redact(message: str, token: str | None) -> str:
    """Quita el access token de cualquier mensaje antes de mostrarlo."""
    if token:
        message = message.replace(token, "[REDACTED_TOKEN]")
    return re.sub(r"access_token=[^&\s\"']+", "access_token=[REDACTED_TOKEN]", message)


def _handle_error_payload(payload: dict, token: str, attempt: int, retries: int) -> bool:
    """Si `payload` trae un objeto 'error' (la Graph API a veces lo manda
    con HTTP 200, no solo en respuestas 4xx/5xx), decide si hay que
    reintentar (True) o lanzar GraphAPIError (False -> ya lanzó)."""
    error = payload.get("error")
    if not error:
        return False
    error_code = error.get("code")
    error_message = error.get("message", str(error))
    if error_code in RETRYABLE_ERROR_CODES and attempt <= retries:
        return True
    raise GraphAPIError(redact(f"Graph API error ({error_code}): {error_message}", token)) from None


def _http_get_with_retry(url: str, token: str, throttle: float, retries: int) -> dict:
    """GET con throttling fijo y backoff exponencial en errores retryable
    (rate limit / transitorios). `url` ya trae la query completa.

    La Graph API a veces devuelve un objeto 'error' con status HTTP 200
    (no solo como HTTPError 4xx/5xx) — sin chequear eso, una respuesta de
    rate-limit se leía como página vacía en vez de fallar/reintentar."""
    attempt = 0
    while True:
        time.sleep(throttle)
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            attempt += 1
            if _handle_error_payload(payload, token, attempt, retries):
                time.sleep(min(60, 2 ** attempt))
                continue
            return payload
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(body)
                error_code = payload.get("error", {}).get("code")
                error_message = payload.get("error", {}).get("message", body)
            except json.JSONDecodeError:
                error_code = None
                error_message = body

            attempt += 1
            if error_code in RETRYABLE_ERROR_CODES and attempt <= retries:
                time.sleep(min(60, 2 ** attempt))
                continue

            raise GraphAPIError(redact(f"Graph API error ({error_code}): {error_message}", token)) from None
        except urllib.error.URLError as exc:
            attempt += 1
            if attempt <= retries:
                time.sleep(min(60, 2 ** attempt))
                continue
            raise GraphAPIError(redact(f"Fallo de red hablando con la Graph API: {exc}", token)) from None


def graph_request(path: str, token: str, params: dict | None = None,
                   throttle: float = 0.4, retries: int = 5) -> dict:
    query = dict(params or {})
    query["access_token"] = token
    url = f"{GRAPH_API_BASE}/{path}?{urllib.parse.urlencode(query)}"
    return _http_get_with_retry(url, token, throttle, retries)


def paginate_all(first_page: dict, token: str, throttle: float, retries: int) -> list:
    items = list(first_page.get("data", []))
    next_url = first_page.get("paging", {}).get("next")
    while next_url:
        page = _http_get_with_retry(next_url, token, throttle, retries)
        items.extend(page.get("data", []))
        next_url = page.get("paging", {}).get("next")
    return items


def get_triggers() -> list[str]:
    raw = os.environ.get("IG_TRIGGERS", "")
    custom = [t.strip().lower() for t in raw.split(",") if t.strip()]
    return sorted(set(DEFAULT_TRIGGERS) | set(custom))


def tag_comment(comment: dict, owner_username: str | None, triggers: list[str]) -> dict:
    text = (comment.get("text") or "").lower()
    username = comment.get("username", "")
    is_owner = bool(owner_username) and username.lower() == owner_username.lower()
    matched = next((t for t in triggers if t in text), None)
    comment["is_from_owner"] = is_owner
    comment["is_trigger"] = matched is not None
    comment["matched_trigger"] = matched
    return comment


def fetch_comments(media_id: str, token: str, owner_username: str | None,
                    throttle: float, retries: int) -> list[dict]:
    triggers = get_triggers()
    first = graph_request(
        f"{media_id}/comments", token,
        {"fields": "id,text,username,timestamp,like_count,replies{id,text,username,timestamp,like_count}"},
        throttle, retries,
    )
    raw_comments = paginate_all(first, token, throttle, retries)

    flat: list[dict] = []
    for comment in raw_comments:
        replies = comment.pop("replies", {}).get("data", []) if isinstance(comment.get("replies"), dict) else []
        flat.append(tag_comment(dict(comment), owner_username, triggers))
        for reply in replies:
            reply["in_reply_to"] = comment.get("id")
            flat.append(tag_comment(dict(reply), owner_username, triggers))
    return flat


INSIGHT_METRIC_CANDIDATES = [
    "reach", "views", "saved", "shares", "total_interactions", "likes",
    "comments", "ig_reels_avg_watch_time", "ig_reels_video_view_total_time",
    "reels_skip_rate",
]


def fetch_insights(media_id: str, token: str, throttle: float, retries: int) -> dict:
    """Prueba metricas una por una: la Graph API cambia el set valido de
    metricas de reels entre versiones y por tipo de media."""
    results: dict = {}
    for metric in INSIGHT_METRIC_CANDIDATES:
        try:
            data = graph_request(f"{media_id}/insights", token, {"metric": metric}, throttle, retries)
            for entry in data.get("data", []):
                values = entry.get("values", [])
                if values:
                    results[entry["name"]] = values[0].get("value")
        except GraphAPIError as exc:
            results.setdefault("_errors", []).append(f"{metric}: {exc}")
    return results


def fetch_media_list(account_id: str, token: str, limit: int, throttle: float, retries: int) -> list[dict]:
    first = graph_request(
        f"{account_id}/media", token,
        {"fields": "id,media_type,media_product_type,caption,permalink,timestamp,like_count,comments_count", "limit": min(limit, 100)},
        throttle, retries,
    )
    items = paginate_all(first, token, throttle, retries)
    return items[:limit]


def fetch_owner_username(account_id: str, token: str, throttle: float, retries: int) -> str | None:
    try:
        data = graph_request(account_id, token, {"fields": "username"}, throttle, retries)
        return data.get("username")
    except GraphAPIError:
        return None


def cmd_list(args, token: str) -> None:
    items = fetch_media_list(args.account_id, token, args.limit, args.throttle, args.retries)
    print(json.dumps(items, ensure_ascii=False, indent=2))


def cmd_comments(args, token: str) -> None:
    owner = fetch_owner_username(args.account_id, token, args.throttle, args.retries)
    comments = fetch_comments(args.media_id, token, owner, args.throttle, args.retries)
    print(json.dumps(comments, ensure_ascii=False, indent=2))


def cmd_insights(args, token: str) -> None:
    insights = fetch_insights(args.media_id, token, args.throttle, args.retries)
    print(json.dumps(insights, ensure_ascii=False, indent=2))


def build_bundle_for_media(media: dict, token: str, owner_username: str | None,
                            throttle: float, retries: int) -> dict:
    media_id = media["id"]
    comments = fetch_comments(media_id, token, owner_username, throttle, retries)
    insights = fetch_insights(media_id, token, throttle, retries)

    real_comments = [c for c in comments if not c["is_from_owner"]]
    lead_candidates = [c for c in real_comments if c["is_trigger"]]

    return {
        "media": media,
        "insights": insights,
        "comments": comments,
        "counts": {
            "total_comments": len(comments),
            "real_comments": len(real_comments),
            "lead_candidates": len(lead_candidates),
        },
    }


def cmd_bundle(args, token: str) -> None:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    owner = fetch_owner_username(args.account_id, token, args.throttle, args.retries)

    if args.recent:
        media_list = fetch_media_list(args.account_id, token, args.recent, args.throttle, args.retries)
    else:
        media_list = [{"id": media_id} for media_id in args.media_ids]
        # completar datos del media si solo tenemos el id
        media_list = [
            graph_request(m["id"], token, {"fields": "id,media_type,media_product_type,caption,permalink,timestamp,like_count,comments_count"}, args.throttle, args.retries)
            for m in media_list
        ]

    index = []
    for media in media_list:
        if not args.quiet:
            print(f"-> {media['id']}", file=sys.stderr)
        bundle = build_bundle_for_media(media, token, owner, args.throttle, args.retries)
        out_path = out_dir / f"{media['id']}.json"
        out_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        index.append({"id": media["id"], "file": out_path.name, "counts": bundle["counts"]})

    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(index, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Graph API CLI para reels de Instagram (solo tu cuenta, tu token).")
    parser.add_argument("--env", default=None, help="Ruta a un .env alternativo (default: junto a este script)")
    parser.add_argument("--account-id", default=None, help="Override de INSTAGRAM_BUSINESS_ACCOUNT_ID")
    parser.add_argument("--throttle", type=float, default=0.4, help="Segundos de espera entre llamadas (default 0.4)")
    parser.add_argument("--retries", type=int, default=5, help="Reintentos ante rate limit / errores transitorios")
    parser.add_argument("-q", "--quiet", action="store_true", help="Menos output de progreso")

    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="Lista los ultimos reels/media de la cuenta")
    p_list.add_argument("--limit", type=int, default=30)
    p_list.set_defaults(func=cmd_list)

    p_comments = sub.add_parser("comments", help="Comentarios + replies de un media")
    p_comments.add_argument("media_id")
    p_comments.set_defaults(func=cmd_comments)

    p_insights = sub.add_parser("insights", help="Insights de un media")
    p_insights.add_argument("media_id")
    p_insights.set_defaults(func=cmd_insights)

    p_bundle = sub.add_parser("bundle", help="Media + insights + comentarios tagueados a JSON")
    p_bundle.add_argument("media_ids", nargs="*", help="IDs concretos (omitir si usas --recent)")
    p_bundle.add_argument("--recent", type=int, default=0, help="Los N reels mas recientes en vez de IDs")
    p_bundle.add_argument("--out", default="out", help="Carpeta de salida (default: out/)")
    p_bundle.set_defaults(func=cmd_bundle)

    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = build_parser()
    args = parser.parse_args(argv)

    script_dir = Path(__file__).resolve().parent.parent
    env_path = Path(args.env) if args.env else script_dir / ".env"
    load_env(env_path)

    token = os.environ.get(TOKEN_ENV_VAR)
    if not token:
        print(f"Falta {TOKEN_ENV_VAR}. Configuralo en {env_path} o como variable de entorno.", file=sys.stderr)
        return 2

    args.account_id = args.account_id or os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    if args.command in {"list", "bundle"} and not args.account_id:
        print("Falta INSTAGRAM_BUSINESS_ACCOUNT_ID (env o --account-id).", file=sys.stderr)
        return 2

    try:
        args.func(args, token)
    except GraphAPIError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
