"""
RFAM Toolbox - Setup Configuration
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="rfam-toolbox",
    version="1.0.0",
    author="Matthew L. McCoy",
    author_email="matthew.mccoy@gatech.edu",
    description="Tools for Radio Frequency and Binder Jet Additive Manufacturing process analysis",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/mattlmccoy/rfam-toolbox",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Image Processing",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.7",
    install_requires=[
        "opencv-python>=4.5.0",
        "numpy>=1.20.0",
        "matplotlib>=3.4.0",
        "pandas>=1.3.0",
        "scikit-image>=0.18.0",
    ],
    extras_require={
        "pdf": ["pdf2image>=1.14.0"],
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "black>=21.0",
            "flake8>=3.9",
        ],
    },
    entry_points={
        "console_scripts": [
            "rfam-toolbox=rfam_toolbox.launcher:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["*.png", "*.pdf"],
    },
)
