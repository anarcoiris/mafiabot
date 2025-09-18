# debug_game_manager.py
import sys, os, inspect, importlib, glob

project_root = os.getcwd()
print("Working dir:", project_root)
print("Python:", sys.executable, sys.version)
print()

# Buscar definiciones de 'class GameManager' en todos los .py
matches = []
for p in glob.glob("**/*.py", recursive=True):
    try:
        txt = open(p, "r", encoding="utf-8").read()
    except Exception:
        continue
    if "class GameManager" in txt:
        matches.append(p)
print("Files containing 'class GameManager':")
for f in matches:
    print("  -", f)
print()

# Intentar importar el main/modular (prueba nombres comunes)
candidates = ["mafiabot3a_modular", "mafiabot3a", "mafiabot3", "mafiabot", "mafiabot3a_modular.py"]
main_mod = None
for name in ("mafiabot3a_modular", "mafiabot3a", "mafiabot3", "mafiabot"):
    try:
        print(f"Trying import {name} ...", end=" ")
        m = importlib.import_module(name)
        print("OK")
        main_mod = m
        break
    except Exception as e:
        print("FAILED:", type(e).__name__, e)
print()

# Importar módulo game_manager si existe
gm_mod = None
try:
    gm_mod = importlib.import_module("game_manager")
    print("Imported module 'game_manager' from", getattr(gm_mod, "__file__", "<unknown>"))
except Exception as e:
    print("Could not import module 'game_manager':", type(e).__name__, e)
print()

# Inspeccionar GameManager en game_manager module
if gm_mod:
    GM = getattr(gm_mod, "GameManager", None)
    print("game_manager.GameManager:", GM)
    if GM:
        methods = [name for name, _ in inspect.getmembers(GM, predicate=inspect.isfunction)]
        print("Methods on class GameManager:", methods)
    print()

# Buscar variable global GAME in main (if imported)
if main_mod:
    GAME = getattr(main_mod, "GAME", None)
    print("main module:", main_mod.__name__, "GAME present?", GAME is not None)
    if GAME is not None:
        print("GAME repr:", repr(GAME))
        print("GAME type:", type(GAME), "module:", getattr(GAME.__class__, "__module__", None))
        # list methods on the instance
        inst_methods = [name for name, _ in inspect.getmembers(GAME, predicate=inspect.ismethod)]
        print("Instance methods:", inst_methods)
    # Also check if main module defines GameManager class itself
    gm_in_main = getattr(main_mod, "GameManager", None)
    print("main module has class GameManager?", gm_in_main is not None)
    if gm_in_main:
        print("main.GameManager methods:", [n for n,_ in inspect.getmembers(gm_in_main, predicate=inspect.isfunction)])
print()

# If no main module was found, show top-level modules that define GAME
if not main_mod:
    print("No common main module imported. Searching any module that defines GAME variable...")
    found = []
    for p in glob.glob("**/*.py", recursive=True):
        try:
            name = os.path.splitext(os.path.basename(p))[0]
            m = importlib.import_module(name)
            if hasattr(m, "GAME"):
                found.append((name, getattr(m, "__file__", None)))
        except Exception:
            pass
    print("Modules with GAME variable:", found)
print()

print("Done. If GAME lacks get_game, inspect above: either the GameManager class is different or GAME was overwritten.")
