import os

# `config.py` reads DEBUG_MODE at import time, so set it before importing `main`
os.environ["DEBUG_MODE"] = "1"
