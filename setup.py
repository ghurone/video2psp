# setup.py
from pathlib import Path

from setuptools import setup, find_packages

long_description = (Path(__file__).parent / "README.md").read_text(encoding="utf-8")

setup(
    name="video2psp",
    version="0.4.0",
    packages=find_packages(),
    url="https://github.com/ghurone/video2psp",
    entry_points={
        "console_scripts": [
            "video2psp=video2psp.psp:main",
        ],
    },
    author="Erick Ghuron",
    author_email="ghuron@usp.br",
    description=(
        "CLI tool to convert videos into PSP-compatible MP4, with interactive "
        "track selection, subtitle burn-in, volume adjustment, and CRF-based "
        "quality control."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    python_requires=">=3.11",
)
