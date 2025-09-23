# models.py
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, Any
import time
import json

@dataclass
class Player:
    user_id: int
    name: str
    role_key: Optional[str] = None
    alive: bool = True
    blocked: bool = False
    silenced: bool = False
    dm_sent_ok: bool = False

    def to_row(self):
        return (self.user_id, self.name, self.role_key, int(self.alive), int(self.blocked), int(self.silenced), int(self.dm_sent_ok))

@dataclass
class Game:
    chat_id: int
    host_id: int
    phase: str = "lobby"
    roles_config: Dict[str,int] = field(default_factory=lambda: {"mafia":1,"ciudadano":3})
    night_seconds: int = 300
    day_seconds: int = 600
    periodic_reminder_seconds: int = 120
    phase_deadline: Optional[int] = None
    players: Dict[int, Player] = field(default_factory=dict)
    night_actions: Dict[str, list] = field(default_factory=dict)
    mafia_votes: Dict[int,int] = field(default_factory=dict)
    pending_action_callbacks: Dict[str,dict] = field(default_factory=dict)
    job_ids: Dict[str,str] = field(default_factory=dict)
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))

    def reset_to_lobby(self):
        self.phase = "lobby"
        self.roles_config = {"mafia": 1, "ciudadano": 3}
        self.phase_deadline = None
        self.night_actions.clear()
        self.mafia_votes.clear()
        self.pending_action_callbacks.clear()
        self.job_ids.clear()
        for p in self.players.values():
            p.role_key = None
            p.alive = True
            p.blocked = False
            p.silenced = False
            p.dm_sent_ok = False
        self.updated_at = int(time.time())

    def to_db_tuple(self):
        return (self.chat_id, self.host_id, self.phase, json.dumps(self.roles_config, ensure_ascii=False),
                self.night_seconds, self.day_seconds, self.periodic_reminder_seconds,
                self.phase_deadline, self.created_at, int(time.time()))

    @classmethod
    def from_db_row(cls, row, players_list):
        (chat_id, host_id, phase, roles_json, night_s, day_s, periodic, deadline, created_at, updated_at) = row
        g = cls(chat_id, host_id)
        g.phase = phase or "lobby"
        try:
            g.roles_config = json.loads(roles_json) if roles_json else g.roles_config
        except:
            pass
        g.night_seconds = night_s or g.night_seconds
        g.day_seconds = day_s or g.day_seconds
        g.periodic_reminder_seconds = periodic or g.periodic_reminder_seconds
        g.phase_deadline = deadline
        g.created_at = created_at or g.created_at
        g.updated_at = updated_at or g.updated_at
        for p in players_list:
            uid, name, role_key, alive, blocked, silenced, dm_sent_ok = p
            g.players[uid] = Player(uid, name, role_key, bool(alive), bool(blocked), bool(silenced), bool(dm_sent_ok))
        return g
