from setuptools import setup, find_packages

APP = ['DexMate.py']  # Replace with the name of your main Python script
DATA_FILES = [
    ('', ['settings.json', 'secret.key', 'credentials.json', 'Readme.md', 'LICENSE']),
]
OPTIONS = {
    'argv_emulation': True,
    'iconfile': 'logo_icns.icns',  # Path to your application icon
}

setup(
    name="DexMate",
    version="1.0.0",
    description="A glucose level monitoring widget using pydexcom API",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="rpimaster",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/DexMate",
    packages=find_packages(),
    install_requires=[
        "pydexcom>=0.2.2",
        "notifypy>=1.0.0",
        "cryptography>=3.4.7"
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "flake8>=3.8",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    include_package_data=True,
    package_data={
        '': ['*.json', '*.md', '*.key', '*.py'],
    },
    entry_points={
        'console_scripts': [
            'dexmate=dexmate.main:main',  # Example entry point
        ],
    },
)
