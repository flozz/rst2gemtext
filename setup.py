#!/usr/bin/env python
# encoding: UTF-8

import os

from setuptools import setup


long_description = ""
if os.path.isfile("README.rst"):
    long_description = open("README.rst", "r", encoding="UTF-8").read()


setup(
    name="rst2gemtext",
    version="0.4.0",
    description="Converts reStructuredText to Gemtext (Gemini markup format)",
    url="https://github.com/flozz/rst2gemtext",
    project_urls={
        "Source Code": "https://github.com/flozz/rst2gemtext",
        "Issues": "https://github.com/flozz/rst2gemtext/issues",
        "Chat": "https://discord.gg/P77sWhuSs4",
        "Donate": "https://github.com/flozz/rst2gemtext#support-this-project",
    },
    license="GPLv3",
    long_description=long_description,
    keywords="restructuredtext rst convert gemtext gmi gemini docutils",
    author="Fabien LOISON",
    py_modules=["rst2gemtext"],
    install_requires=[
        "docutils",
        "pygments",
    ],
    extras_require={
        "dev": [
            "nox",
            "flake8",
            "pytest",
            "black",
        ]
    },
    entry_points={
        "console_scripts": [
            "rst2gemtext = rst2gemtext:main",
        ],
    },
)
