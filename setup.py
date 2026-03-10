# setup.py
from setuptools import find_packages, setup

setup(
    name="HordeForge",
    version="0.1.0",
    description="HordeForge development gateway and pipeline scaffolding",
    author="Your Name",
    author_email="you@example.com",
    packages=find_packages(),
    install_requires=[
        "PyYAML>=6.0",
        "requests>=2.28",
        "openai>=0.27",
        "tiktoken>=0.4",  # если будем использовать OpenAI embeddings
        "fastapi>=0.95",  # для Scheduler Gateway API
        "uvicorn>=0.22",  # для запуска FastAPI
    ],
    entry_points={
        "console_scripts": [
            "hordeforge=cli:main",
        ],
    },
    python_requires=">=3.10",
)
