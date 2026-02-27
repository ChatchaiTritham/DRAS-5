"""
DRAS-5: Dynamic Risk Assessment State Machine

Package configuration for the DRAS-5 framework, which implements a 5-state
risk assessment machine with exponential decay de-escalation and formal
constraint enforcement (C1--C5) for clinical decision support.

Author: Chatchai Tritham (chatchait66@nu.ac.th)
Supervisor: Chakkrit Snae Namahoot (chakkrits@nu.ac.th)
Institution: Department of Computer Science and Information Technology,
             Faculty of Science, Naresuan University,
             Phitsanulok 65000, Thailand
"""

from setuptools import setup, find_packages
from pathlib import Path

readme_path = Path(__file__).parent / "README.md"
long_desc = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

setup(
    name="dras5",
    version="1.0.0",
    author="Chatchai Tritham, Chakkrit Snae Namahoot",
    author_email="chatchait66@nu.ac.th, chakkrits@nu.ac.th",
    description=(
        "DRAS-5: 5-State Dynamic Risk Assessment Machine with "
        "Exponential Decay De-escalation and Provable Safety Guarantees"
    ),
    long_description=long_desc,
    long_description_content_type="text/markdown",
    url="https://github.com/ChatchaiTritham/DRAS-5",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Healthcare Industry",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Scientific/Engineering :: Medical Science Apps.",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=[
        "numpy>=1.21.0",
    ],
    extras_require={
        "viz": [
            "matplotlib>=3.4.0",
            "seaborn>=0.11.0",
        ],
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=3.0.0",
            "matplotlib>=3.4.0",
            "seaborn>=0.11.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "dras5-demo=dras5.cli:demo",
            "dras5-validate=dras5.cli:validate",
        ],
    },
)
