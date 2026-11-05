"""Builds agent/agent_code.zip: the agent code plus its Python packages, ready for AgentCore.
Run it before `terraform apply`, and again whenever agent.py or labels.py changes.
"""
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(HERE, "build")
ZIP_PATH = os.path.join(HERE, "agent_code.zip")
CODE_FILES = ["agent.py", "labels.py", "passages.py"]

# 1. Start with an empty build folder
shutil.rmtree(BUILD_DIR, ignore_errors=True)

# 2. Install the packages for AgentCore's machines (Linux ARM64, Python 3.12), not for this PC
subprocess.run([
    sys.executable, "-m", "pip", "install", "-r", os.path.join(HERE, "requirements.txt"),
    "--target", BUILD_DIR, "--quiet",
    "--platform", "manylinux2014_aarch64", "--platform", "manylinux_2_28_aarch64",
    "--python-version", "3.12", "--implementation", "cp", "--only-binary=:all:",
], check=True)

# 3. Copy our own code next to the packages
for name in CODE_FILES:
    shutil.copy(os.path.join(HERE, name), BUILD_DIR)

# 4. Zip everything (files at the top level of the zip)
with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
    for folder, dirs, files in os.walk(BUILD_DIR):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            full = os.path.join(folder, f)
            z.write(full, os.path.relpath(full, BUILD_DIR))

print(f"Built {ZIP_PATH}: {os.path.getsize(ZIP_PATH) / 1_000_000:.1f} MB")
