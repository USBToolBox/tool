import subprocess

try:
    result = subprocess.run("git describe --tags --always".split(), stdout=subprocess.PIPE)
    BUILD = result.stdout.decode().strip()
except:
    BUILD = None
