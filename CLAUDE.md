# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Mafia Bot** - A complete Telegram bot and GUI application for playing the social deduction game Mafia (also known as Werewolf). The project features 15+ roles across three factions (Town, Mafia, Neutral), night actions, day voting, full persistence with SQLite, and both a Telegram bot interface and a standalone tkinter GUI with bot player support.

## Development Commands

### Running the Application

**Telegram Bot:**
```bash
python bot/main.py
```
Requires `TELEGRAM_TOKEN` in environment or `.env` file.

**GUI (Standalone):**
```bash
python gui/app.py
```

**GUI Debug Mode (reveals all roles):**
```bash
python gui/app.py --debug
```

### Dependencies
```bash
pip install -r requirements.txt
```

### Database
- SQLite database stored at `data/mafia.db`
- Async operations via `aiosqlite`
- No migrations needed for development (schema auto-created)

## Architecture Overview

### Core Principle: Separation of Concerns

This codebase follows a **clean architecture** pattern with strict separation between game logic, persistence, and UI adapters. **NO circular imports** are allowed.

### Layer Structure

```
core/          - Pure game logic (zero dependencies on bot/gui/persistence)
├── models.py  - Data classes: Game, Player, Role, Phase, GameEvent, ChatMessage
├── roles.py   - All 15+ role definitions with faction, abilities, priorities
└── engine.py  - GameEngine class: role assignment, night resolution, vote resolution, victory checks

adapters/      - Abstract interfaces for frontends
└── game_interface.py - GameInterface ABC (send_message, send_broadcast, request_action, update_game_state)

bot/           - Telegram bot implementation (adapter)
├── main.py    - Entry point, bot initialization
├── handlers.py - Command handlers (/crearpartida, /unirme, /empezar, etc.)
├── callbacks.py - Inline button callbacks for night actions and voting
├── jobs.py    - Scheduled tasks (phase timers)
└── telegram_adapter.py - Implements GameInterface for Telegram

gui/           - Tkinter GUI implementation (adapter)
├── app.py     - MafiaGUIApp main window and perspective window management
├── controllers/
│   ├── game_controller.py - GUIGameController: bridges UI and game logic
│   ├── game_state_controller.py - GameStateController: pure game state management with event bus
│   ├── player_perspective.py - PlayerPerspective: implements fog-of-war (what each player can see)
│   └── interface_adapters.py - UI adapters
├── views/     - Tkinter view components (lobby, game, perspective windows)
├── widgets/   - Reusable UI components (player cards, chat widget)
└── bots/      - Bot player AI with multiple difficulty levels

persistence/   - Database layer (async)
├── database.py - Async SQLite repository with aiosqlite
├── repository.py - Repository pattern abstraction
└── migrations.py - Schema definitions
```

### Key Architectural Patterns

#### 1. Dependency Injection
`core/` has **zero imports** from `bot/`, `gui/`, or `persistence/`. All dependencies flow inward:
- Bot/GUI → Core (OK)
- Core → Bot/GUI (FORBIDDEN)

When core needs to trigger UI updates, use callbacks or event buses passed from the outer layers.

#### 2. Adapter Pattern
Both Telegram and GUI implement their own adapters:
- `bot/telegram_adapter.py` implements `GameInterface` for Telegram
- `gui/controllers/game_controller.py` adapts tkinter UI to core game logic
- This allows the same game engine to work with multiple frontends

#### 3. Game State Controller
`gui/controllers/game_state_controller.py` provides:
- Pure game state management (no UI coupling)
- Event bus for pub/sub communication
- Chat message handling with proper channel routing
- Used by GUI controller to isolate game logic from tkinter

#### 4. Player Perspective (Fog of War)
`gui/controllers/player_perspective.py` implements information hiding:
- Each player has a `PlayerPerspective` that filters what they can see
- Determines visible chat channels (general, mafia-only, etc.)
- Controls which game state is visible (alive players, known roles, etc.)
- Used by perspective windows to show player-specific views

#### 5. Night Resolution Pipeline
`core/engine.py` uses a modular resolution pipeline:
1. Apply blocks (roleblock abilities)
2. Apply protections (doctor heals, bodyguard)
3. Convert mafia votes to collective action
4. Process attacks (with immunity, heals, bodyguard sacrifices)
5. Apply blackmail (silencing)
6. Process investigations
7. Cleanup temporary flags

This ensures correct priority ordering and interaction between abilities.

## Important Implementation Details

### Phase Transitions
Phases: `LOBBY → NIGHT → DAY → VOTING → NIGHT → ...` until victory condition met.

- **NIGHT**: Players with night abilities receive action prompts (DMs in Telegram, buttons in GUI). Mafia votes collectively on kill target.
- **DAY**: Open discussion period, no voting yet. Investigative roles may share findings.
- **VOTING**: Players vote on who to lynch. Tied votes result in no lynch.
- **Victory checks** occur after night resolution and after vote resolution.

### Timers
- Configurable in `Game.night_seconds`, `Game.day_seconds`
- GUI uses threaded timers (`_timer_worker`) to auto-advance phases
- Telegram uses APScheduler jobs
- Always stop/cancel timers when transitioning phases

### Bot Players (GUI Only)
Located in `gui/bots/bot_player.py`:
- Three difficulty levels: EASY, NORMAL, HARD
- Bots make decisions via `decide_night_action()` and `decide_day_vote()`
- Investigation results stored on bot instance for later sharing
- Bot actions executed in `GUIGameController.execute_bot_actions()`

### Chat System
`ChatMessage` model supports multiple channels:
- `general`: Everyone can see
- `mafia`: Only mafia members can see
- `system`: System announcements
- Future: private DMs

GUI uses `PlayerPerspective.can_see_chat_message()` to filter chat in perspective windows.

### Perspective Windows (GUI)
Multi-window support for testing:
- Each human player can have their own window showing only what they know
- Menu: "Ventanas" → "Abrir Todas las Perspectivas"
- Bot players don't get perspective windows
- Managed in `MafiaGUIApp.perspective_windows` dict

### Event Handling
`GameStateController` publishes events to event bus:
- `chat`: Chat messages
- `investigation`: Investigation results
- `death`, `lynch`, `bodyguard_death`: Player deaths
- `block`, `heal`, `guard`, `blackmail`: Night actions

`GUIGameController._handle_state_event()` subscribes and routes to UI callbacks. Includes duplicate message detection via `_processed_message_ids`.

## Common Tasks

### Adding a New Role

1. **Define in `core/roles.py`:**
```python
ROLES["new_role"] = Role(
    key="new_role",
    name="Display Name",
    description="What the role does",
    faction=Faction.TOWN,  # or MAFIA, NEUTRAL
    has_night_action=True,
    priority=5,  # Lower = earlier in night resolution
    detective_signature="Suspicious"  # Optional
)
```

2. **Add action type mapping in `gui/controllers/game_controller.py` (line ~215):**
```python
action_map = {
    # ... existing roles ...
    "new_role": "new_action_type"
}
```

3. **Implement resolution in `core/engine.py`:**
   - Add handler in appropriate pipeline step (e.g., `_process_investigations` for investigative roles)
   - Or create new pipeline step if needed

4. **Add UI handlers:**
   - Telegram: `bot/callbacks.py` for inline buttons
   - GUI: Perspective windows auto-generate target selection

### Testing with Bots

Use GUI debug mode to observe all roles:
```bash
python gui/app.py --debug
```

In lobby:
1. Add players (mix of human and bot types)
2. Click "Tipo" dropdown to assign bot difficulty
3. Start game
4. Use "Ventanas" menu to open perspective windows for human players

### Working with Database

Telegram bot uses `persistence/database.py` (async):
- `GameRepository` handles CRUD operations
- Auto-reconnects on failures
- Uses `aiosqlite` for async SQLite

GUI currently runs in-memory (no persistence), but shares the same `Game` model so database integration would be straightforward.

## Common Pitfalls

1. **Circular Imports**: Never import from bot/gui inside core/. Use dependency injection.

2. **Phase Timer Conflicts**: Always stop existing timers before starting new ones. Use `_stop_timer_thread()`.

3. **Duplicate Chat Messages**: GUI controller uses `_processed_message_ids` to deduplicate. Don't manually append to `self.messages` if using `state_controller.register_chat_message()`.

4. **Missing AttributeError**: Always use `hasattr()` or `getattr()` with defaults when accessing optional attributes on `Game` or `Player` objects, especially for fields that may not be initialized.

5. **UI Thread Safety**: In GUI controller, use `self.app.root.after(0, callback)` when updating UI from background threads.

6. **Bot Instance Cleanup**: When game ends, clear `self.bots` and `self.perspectives` dicts.

## Code Style

- Type hints on all public methods
- Docstrings for non-obvious functions
- Logger calls for significant state changes
- `try/except` with `logger.exception()` for error handling
- Defensive programming: check if game exists, if player exists, if alive, etc.
- to memorize
- to memorize
- to memorize