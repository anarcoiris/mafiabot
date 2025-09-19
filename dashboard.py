#!/usr/bin/env python3
"""
dashboard.py – Dashboard Flask para Mafia Bot
Incluye:
- Autenticación flexible por token
- Soporte chat_id positivos/negativos (Telegram grupos usan negativos)
- Fallback: reenviar rol en grupo si no llega por DM
- Reset de partida a estado "lobby"
- Visualización extendida de partidas y jugadores
"""

import os
import asyncio
from typing import Optional
from flask import (
    Flask, render_template_string, request, redirect, url_for,
    Response, jsonify, current_app
)

# En lugar de importar main (evita import circular),
# permitimos que main inicialice estos valores llamando init_dashboard(...)
GAME = None
ROLES = None
clamp_phase_seconds = None
application = None

def init_dashboard(game_obj, roles_obj, clamp_fn, application_obj, dash_token=None, dash_port=None):
    """Inicializa las referencias que dashboard necesita desde main sin importar main."""
    global GAME, ROLES, clamp_phase_seconds, application, DASH_TOKEN, DASH_PORT
    GAME = game_obj
    ROLES = roles_obj
    clamp_phase_seconds = clamp_fn
    application = application_obj
    if dash_token is not None:
        DASH_TOKEN = dash_token
    if dash_port is not None:
        DASH_PORT = dash_port

# ----------------------------
# Config
# ----------------------------
DASH_PORT = int(os.environ.get("MAFIA_DASH_PORT", "8006"))
DASH_TOKEN = os.environ.get(
    "MAFIA_DASH_TOKEN", "changeme_in_prod"
)

flask_app = Flask("mafia_dashboard")

# ----------------------------
# Helpers
# ----------------------------
def _clean_token(t: Optional[str]) -> Optional[str]:
    if not t:
        return None
    t = t.strip()
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1]
    return t

def check_dash_auth(req) -> bool:
    token = req.args.get("token") \
        or req.form.get("token") \
        or req.headers.get("X-DASH-TOKEN") \
        or req.headers.get("Authorization")
    if token and token.startswith("Bearer "):
        token = token.split(" ", 1)[1]
    token = _clean_token(token)
    return token == DASH_TOKEN

def _get_game_try_both(chat_id):
    """Busca un juego por id o su negativo."""
    try:
        g = GAME.get_game(chat_id)
        if g:
            return g, chat_id
    except Exception:
        current_app.logger.exception("Error buscando juego con chat_id %s", chat_id)

    try:
        alt = -int(chat_id)
        g = GAME.get_game(alt)
        if g:
            return g, alt
    except Exception:
        current_app.logger.debug("No existe juego con id alternativo")

    return None, None

# ----------------------------
# Template HTML
# ----------------------------
DASH_TMPL = """
<!doctype html>
<title>Mafia Dashboard</title>
<h1>Partidas activas</h1>
<p>Protegido con token: env MAFIA_DASH_TOKEN</p>
{% for g in games %}
  <div style="border:1px solid #ccc;padding:10px;margin:10px;">
    <h3>Chat {{g.chat_id}} (url id={{g.chat_id_abs}}) - fase: {{g.phase}}</h3>
    <p>Host: {{g.host_id}} | Noche: {{g.night_seconds//60}}m | Día: {{g.day_seconds//60}}m</p>
    <ul>
      {% for p in g.players %}
        <li>
          {{p.name}} - {{'VIVO' if p.alive else 'MUERTO'}} - rol: {{p.role}}
          {% if not p.dm_sent_ok %}
            ⚠️ <a href="{{ url_for('dash_resend_role', chat_id=g.chat_id_abs, user_id=p.user_id, token=token) }}">Reenviar rol al grupo</a>
          {% endif %}
        </li>
      {% endfor %}
    </ul>

    <form method="post" action="{{ url_for('dash_edit', chat_id=g.chat_id_abs) }}">
      <input type="hidden" name="token" value="{{ token }}">
      Night(min): <input name="night" value="{{g.night_seconds//60}}">
      Day(min): <input name="day" value="{{g.day_seconds//60}}">
      <input type="submit" value="Actualizar">
    </form>

    <form method="post" action="{{ url_for('dash_force', chat_id=g.chat_id_abs) }}">
      <input type="hidden" name="token" value="{{ token }}">
      <input type="submit" value="Forzar resolución de noche">
    </form>

    <form method="post" action="{{ url_for('dash_reset_lobby', chat_id=g.chat_id_abs) }}">
      <input type="hidden" name="token" value="{{ token }}">
      <input type="submit" value="Resetear a Lobby">
    </form>
  </div>
{% endfor %}
"""

# ----------------------------
# Rutas
# ----------------------------
@flask_app.route("/")
def dash_home():
    if not check_dash_auth(request):
        return Response("Unauthorized", status=401)
    games = []
    with GAME._lock:
        for g in GAME._games.values():
            players = []
            for uid, p in g.players.items():
                players.append({
                    "user_id": uid,
                    "name": p.name,
                    "alive": p.alive,
                    "role": ROLES.get(p.role_key).name if p.role_key else "?",
                    "dm_sent_ok": getattr(p, "dm_sent_ok", False),
                })
            games.append({
                "chat_id": g.chat_id,
                "chat_id_abs": abs(g.chat_id),
                "phase": g.phase,
                "host_id": g.host_id,
                "night_seconds": g.night_seconds,
                "day_seconds": g.day_seconds,
                "players": players,
            })
    return render_template_string(DASH_TMPL, games=games, token=DASH_TOKEN)

@flask_app.route("/game/<int:chat_id>/estado", methods=["GET"])
def web_estado(chat_id):
    g, used_id = _get_game_try_both(chat_id)
    if not g:
        return jsonify({"error":"no game"}), 404
    players = [{"user_id": p.user_id, "name": p.name, "alive": p.alive,
                "role": (p.role_key if not p.alive else None)} for p in g.players.values()]
    return jsonify({
        "chat_id": g.chat_id,
        "queried_id": chat_id,
        "used_id": used_id,
        "phase": g.phase,
        "players": players,
        "night_seconds": g.night_seconds,
        "day_seconds": g.day_seconds
    })

@flask_app.route("/admin/list_games", methods=["GET"])
def admin_list_games():
    if not check_dash_auth(request):
        return Response("Unauthorized", status=401)
    games = []
    with GAME._lock:
        for g in GAME._games.values():
            games.append({
                "chat_id": g.chat_id,
                "phase": g.phase,
                "host_id": g.host_id,
                "night_seconds": g.night_seconds,
                "day_seconds": g.day_seconds,
                "players": [{"user_id": p.user_id, "name": p.name,
                             "alive": p.alive, "role": p.role_key} for p in g.players.values()]
            })
    return jsonify({"games": games})

@flask_app.route("/edit/<int:chat_id>", methods=["POST"])
def dash_edit(chat_id):
    if not check_dash_auth(request):
        return Response("Unauthorized", status=401)
    g, used_id = _get_game_try_both(chat_id)
    if not g:
        return jsonify({"error": "game_not_found"}), 404
    try:
        n_raw = request.form.get("night")
        d_raw = request.form.get("day")
        if n_raw is not None:
            g.night_seconds = clamp_phase_seconds(int(n_raw) * 60)
        if d_raw is not None:
            g.day_seconds = clamp_phase_seconds(int(d_raw) * 60)
        GAME._persist_game(g)
    except Exception:
        current_app.logger.exception("Error en dash_edit")
        return jsonify({"error": "server_error"}), 500
    return redirect(url_for("dash_home") + "?token=" + DASH_TOKEN)

@flask_app.route("/force_resolve/<int:chat_id>", methods=["POST"])
def dash_force(chat_id):
    if not check_dash_auth(request):
        return Response("Unauthorized", status=401)
    g, _ = _get_game_try_both(chat_id)
    if not g:
        return jsonify({"error":"no game"}), 404
    from mafia_bot2_fixed import resolve_night
    asyncio.create_task(resolve_night(g, application))
    return redirect(url_for("dash_home") + "?token=" + DASH_TOKEN)

@flask_app.route("/reset_lobby/<int:chat_id>", methods=["POST"])
def dash_reset_lobby(chat_id):
    if not check_dash_auth(request):
        return Response("Unauthorized", status=401)
    g, _ = _get_game_try_both(chat_id)
    if not g:
        return jsonify({"error":"no game"}), 404
    g.phase = "lobby"
    g.roles_config = {"mafia": 1, "ciudadano": 3}
    g.night_actions.clear()
    g.mafia_votes.clear()
    g.pending_action_callbacks.clear()
    g.phase_deadline = None
    g.job_ids.clear()
    for p in g.players.values():
        p.role_key = None
        p.alive = True
        p.blocked = False
        p.silenced = False
    GAME._persist_game(g)
    return redirect(url_for("dash_home") + "?token=" + DASH_TOKEN)

@flask_app.route("/resend_role/<int:chat_id>/<int:user_id>")
def dash_resend_role(chat_id, user_id):
    if not check_dash_auth(request):
        return Response("Unauthorized", status=401)
    g, _ = _get_game_try_both(chat_id)
    if not g:
        return "Not found", 404
    p = g.players.get(user_id)
    if not p:
        return "Player not found", 404
    role = ROLES.get(p.role_key)
    if not role:
        return "Role not assigned", 400
    asyncio.create_task(application.bot.send_message(
        g.chat_id,
        f"⚠️ {p.name}, no recibiste tu rol en privado.\n"
        f"Tu rol es: *{role.name}*\n{role.description}",
        parse_mode="Markdown"
    ))
    return redirect(url_for("dash_home") + "?token=" + DASH_TOKEN)

# ----------------------------
# Run
# ----------------------------
def run_flask():
    flask_app.run(host="0.0.0.0", port=DASH_PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    run_flask()
