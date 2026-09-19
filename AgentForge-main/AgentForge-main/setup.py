from pathlib import Path

from setuptools import find_packages, setup


BASE_DIR = Path(__file__).parent.resolve()

_README_PATH = BASE_DIR / "README.md"
README = _README_PATH.read_text(encoding="utf-8") if _README_PATH.exists() else ""


setup(
    name="agentforge",
    version="0.1.0",
    description="A production grade AI Software Engineering Platform powered by LangGraph, LangSmith, and MCP.",
    long_description=README,
    long_description_content_type="text/markdown",
    author="Naman Gupta",
    license="MIT",
    python_requires=">=3.11",
    packages=find_packages(
        exclude=[
            "tests",
            "tests.*",
            "docs",
            "frontend",
            "docker",
        ]
    ),
    include_package_data=True,
    zip_safe=False,
    install_requires=[],
    entry_points={
        "console_scripts": [
            "agentforge=backend.cli.main:main",
        ],
    },
    extras_require={
        "dev": [
            "black",
            "isort",
            "ruff",
            "pytest",
            "pytest-asyncio",
            "pytest-cov",
            "mypy",
            "pre-commit",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)