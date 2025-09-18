# streamlit_admin.py
import streamlit as st
import requests

BOT_ADMIN_URL = st.secrets.get("bot_url", "http://192.168.1.131:8006")  # cambia a tu URL
ADMIN_TOKEN = st.secrets.get("admin_token", "pon_aqui_tu_token")

st.title("Admin Mafia - Streamlit")

st.write("Conexión a bot:", BOT_ADMIN_URL)

# list games (assume you expose endpoint /admin/list_games that returns games)
if st.button("Actualizar lista de partidas"):
    try:
        r = requests.get(f"{BOT_ADMIN_URL}/admin/list_games", params={"token": ADMIN_TOKEN}, timeout=5)
        r.raise_for_status()
        games = r.json().get("games", [])
    except Exception as e:
        st.error(f"Error obteniendo partidas: {e}")
        games = []
    st.session_state["games"] = games

games = st.session_state.get("games", [])
for g in games:
    st.subheader(f"Chat {g['chat_id']} (host {g.get('host_id')})")
    night = st.number_input(f"Noche ({g['chat_id']})", value=g.get("night_seconds",300), key=f"night_{g['chat_id']}")
    day = st.number_input(f"Día ({g['chat_id']})", value=g.get("day_seconds",600), key=f"day_{g['chat_id']}")
    if st.button("Actualizar tiempos", key=f"upd_{g['chat_id']}"):
        payload = {"chat_id": g["chat_id"], "night_seconds": int(night), "day_seconds": int(day)}
        try:
            r = requests.post(f"{BOT_ADMIN_URL}/admin/update_times", json=payload, params={"token": ADMIN_TOKEN}, timeout=5)
            r.raise_for_status()
            st.success("Actualizado")
        except Exception as e:
            st.error(f"Error al actualizar: {e}")
