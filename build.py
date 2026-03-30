"""Build NANTA into a standalone desktop app using PyInstaller."""

import PyInstaller.__main__
import os

here = os.path.dirname(os.path.abspath(__file__))

# Packages that are NOT needed by NANTA but get dragged in
# from the global Python environment
EXCLUDES = [
    # ML / deep learning
    "torch", "torchvision", "torchaudio",
    "tensorflow", "keras",
    "sklearn", "scikit-learn",
    "xgboost", "lightgbm",
    "timm", "pytorch_lightning",
    "transformers",
    # Computer vision
    "cv2", "opencv-python",
    "skimage", "scikit-image",
    # Data / visualization
    "pandas", "numpy", "scipy",
    "matplotlib", "bokeh", "altair", "plotly", "seaborn",
    "sympy",
    # Geospatial
    "geopandas", "shapely", "fiona", "pyproj",
    # NLP extras
    "nltk", "spacy", "langchain",
    # Browser / UI (not needed — we use pywebview)
    "playwright", "selenium", "gradio", "streamlit",
    "pygame", "tkinter",
    # Notebooks / IDE
    "jupyter", "notebook", "ipython", "IPython",
    "ipykernel", "ipywidgets",
    # Database / ORM
    "sqlalchemy", "psycopg2", "pymysql",
    # Other
    "faiss", "faiss_cpu",
    "llama_cpp",
    "sounddevice",
    "librosa",
    "flask", "django",
    "sentry_sdk",
    "google.cloud",
    "rdflib",
    "numexpr",
    "pyzmq", "zmq",
    "lark",
    "apscheduler",
]

args = [
    os.path.join(here, "launcher.py"),
    "--name", "NANTA",
    "--onedir",
    "--windowed",
    # Include all project packages and web assets
    "--add-data", f"{os.path.join(here, 'core')};core",
    "--add-data", f"{os.path.join(here, 'platforms')};platforms",
    "--add-data", f"{os.path.join(here, 'services')};services",
    "--add-data", f"{os.path.join(here, 'web')};web",
    # Hidden imports that PyInstaller may miss
    "--hidden-import", "telegram",
    "--hidden-import", "telegram.ext",
    "--hidden-import", "discord",
    "--hidden-import", "discord.ext.commands",
    "--hidden-import", "dotenv",
    "--hidden-import", "aiosqlite",
    "--hidden-import", "httpx",
    "--hidden-import", "trafilatura",
    "--hidden-import", "yt_dlp",
    "--hidden-import", "faster_whisper",
    "--hidden-import", "ctranslate2",
    "--hidden-import", "huggingface_hub",
    "--hidden-import", "tokenizers",
    "--hidden-import", "webview",
    "--hidden-import", "fastapi",
    "--hidden-import", "uvicorn",
    "--hidden-import", "starlette",
    "--hidden-import", "bottle",
    # Output directory
    "--distpath", os.path.join(here, "dist"),
    "--workpath", os.path.join(here, "build"),
    "--specpath", here,
    # Overwrite previous build
    "--noconfirm",
]

# Add all excludes
for pkg in EXCLUDES:
    args.extend(["--exclude-module", pkg])

PyInstaller.__main__.run(args)
