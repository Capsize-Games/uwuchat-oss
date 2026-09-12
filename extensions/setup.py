"""Setup for AIRunner extensions package.

Install in development mode::

    pip install -e .

Install with auth extension dependencies::

    pip install -e ".[auth]"

Install with fastsearch extension dependencies::

    pip install -e ".[fastsearch]"

Install fastsearch with test dependencies::

    pip install -e ".[fastsearch-test]"

Install with all extensions::

    pip install -e ".[all]"
"""

from setuptools import find_packages, setup

setup(
    name="airunner-extensions",
    version="1.0.0",
    description="Extensions for the AI Runner platform",
    author="Capsize Games",
    packages=find_packages(),
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=[
        # All extensions share the core framework
    ],
    extras_require={
        "auth": [
            "pyjwt>=2.8",
            "argon2-cffi>=23.1",
        ],
        "fastsearch": [
            # No extra runtime deps — aiohttp is provided by airunner core
        ],
        "fastsearch-test": [
            "pytest>=7.0",
            "pytest-asyncio>=0.21",
        ],
        "all": [
            "pyjwt>=2.8",
            "argon2-cffi>=23.1",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
