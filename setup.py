# mypy: disable-error-code="import-untyped"
#!/usr/bin/env python
"""Setup script for the project."""

import re

from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as f:
    long_description: str = f.read()


with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements: list[str] = f.read().splitlines()

with open("requirements-dev.txt", "r", encoding="utf-8") as f:
    requirements_dev: list[str] = f.read().splitlines()

with open("firmware/__init__.py", "r", encoding="utf-8") as fh:
    version_re = re.search(r"^__version__ = \"([^\"]*)\"", fh.read(), re.MULTILINE)
assert version_re is not None, "Could not find version in firmware/__init__.py"
version: str = version_re.group(1)


setup(
    name="firmware",
    version=version,
    description="The firmware project",
    author="Benjamin Bolte",
    url="https://github.com/kscalelabs/pyfirmware",
    license="MIT",
    long_description=long_description,
    long_description_content_type="text/markdown",
    python_requires=">=3.11",
    install_requires=requirements,
    extras_require={"dev": requirements_dev},
    packages=find_packages(include=["firmware", "firmware.*"]),
    package_data={"firmware": ["py.typed"]},
    scripts=[
        "scripts/kbot-deploy",
        "scripts/kbot-run",
        "scripts/kbot-sine",
        "scripts/_set_can_and_max_torques.sh",
    ],
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Operating System :: POSIX :: Linux",
        "Intended Audience :: Developers",
        "Topic :: Software Development",
    ],
)
