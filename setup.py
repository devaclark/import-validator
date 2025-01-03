from setuptools import setup, find_packages

setup(
    name="import_validator",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "rich>=13.0.0",
        "networkx>=3.0",
        "matplotlib>=3.7.0",
        "tomli>=2.0.0",
    ],
    entry_points={
        'console_scripts': [
            'import-validator=src.__main__:run_main',
        ],
    },
    package_data={
        'src': ['templates/*.html'],
    },
) 