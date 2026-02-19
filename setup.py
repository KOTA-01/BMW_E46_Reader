#!/usr/bin/env python3
"""
BMW E46 M3 Reader - Setup Script
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text() if readme_path.exists() else ""

setup(
    name="bmw-e46-reader",
    version="0.1.0",
    author="BMW E46 Reader Contributors",
    description="Read diagnostic data from BMW E46 M3 via K+DCAN cable",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/BMW_E46_Reader",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "pyserial>=3.5",
        "python-OBD>=0.7.1",
        "pandas>=2.0.0",
        "click>=8.1.0",
        "tqdm>=4.65.0",
        "pyyaml>=6.0",
        "loguru>=0.7.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "e46-reader=bmw_e46_reader.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Hardware :: Hardware Drivers",
    ],
    keywords="bmw e46 m3 obd obd2 diagnostics smg can kline",
)
