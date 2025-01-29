# setup.py
from setuptools import setup, find_packages

setup(
    name="video2psp",
    version="0.1.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "video2psp=video2psp.psp:main",
        ],
    },
    author="Erick Ghuron",
    author_email="ghuron@usp.br",
    description="A CLI tool to convert video to PSP MP4 with user-selected audio and subtitle tracks.",
    python_requires=">=3.11",
)
