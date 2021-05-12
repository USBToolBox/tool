import subprocess
from pathlib import Path


def write_version():
    try:
        result = subprocess.run("git describe --tags --always".split(), stdout=subprocess.PIPE)
        BUILD = result.stdout.decode().strip()
    except:
        BUILD = None

    Path("Scripts/_build.py").write_text(f"BUILD = {repr(BUILD)}")
