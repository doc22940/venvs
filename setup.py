import os

from setuptools import find_packages, setup


with open(os.path.join(os.path.dirname(__file__), "README.rst")) as readme:
    long_description = readme.read()

classifiers = [
    "Development Status :: 3 - Alpha",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python",
    "Programming Language :: Python :: 2.7",
    "Programming Language :: Python :: 3.4",
    "Programming Language :: Python :: 2",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: Implementation :: CPython",
    "Programming Language :: Python :: Implementation :: PyPy",
]

setup(
    name="mkenv",
    packages=find_packages(),
    setup_requires=["vcversioner"],
    entry_points={
        "console_scripts": [
            "mkenv = mkenv.make:run",
            "mkvenv = mkenv.make:run",
            "findenv = mkenv.find:run",
            "findvenv = mkenv.find:run",
            "rmenv = mkenv.remove:run",
            "rmvenv = mkenv.remove:run",
        ],
    },
    install_requires=["appdirs", "betterpath", "virtualenv"],
    author="Julian Berman",
    author_email="Julian@GrayVines.com",
    classifiers=classifiers,
    license="MIT",
    long_description=long_description,
    url="https://github.com/Julian/mkenv",
    description="A simpler tool for creating venvs in a central location",
    vcversioner={"version_module_paths" : ["mkenv/__init__.py"]},
)
