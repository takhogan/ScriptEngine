from setuptools import setup, find_packages

setup(
    name="script-engine",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        'certifi>=2023.11.17',
        'opencv-python>=4.9.0.80',
        'numpy>=1.26.3',
        'PyAutoGUI>=0.9.54',
        'pymongo>=4.6.1',
        'python-dateutil>=2.8.2',
        'scikit-image>=0.22.0',
        'scipy>=1.11.4',
        'cx_Freeze>=6.15.12',
        # Add other dependencies from setup/venv_requirements.txt
    ],
    entry_points={
        'console_scripts': [
            'script-engine=ScriptEngine.script_manager:main',
            'script-log-preview=ScriptEngine.script_log_preview_generator:main',
            'script-messaging=ScriptEngine.messaging_helper:main',
        ],
    },
    python_requires='>=3.8',
    author="Your Name",
    author_email="your.email@example.com",
    description="Backend engine for Script Studio",
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    url="https://github.com/takhogan/ScriptEngine",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)