"""
py2app setup for Hawker.app

Run from the repo root:
    bash mac/build.sh
"""

from setuptools import setup

APP     = ["_build/menubar.py"]
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        # Menu bar app — no Dock icon
        "LSUIElement": True,
        "NSPrincipalClass": "NSApplication",
        "CFBundleName": "Hawker",
        "CFBundleDisplayName": "Hawker",
        "CFBundleIdentifier": "com.mendelrosenberg.hawker",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0",
        # Permission usage descriptions shown in System Settings
        "NSScreenCaptureUsageDescription":
            "Hawker takes screenshots when you visit social media sites.",
        "NSAppleEventsUsageDescription":
            "Hawker reads your browser's URL to detect social media visits.",
    },
    "packages": ["rumps", "PIL"],
    "includes": [
        "AppKit", "Foundation",
        "Quartz", "Vision",
        "daemon",   # daemon.py bundled as a module
    ],
    "iconfile": "../mac/icon.icns",  # optional — see build.sh
}

setup(
    app=APP,
    data_files=[("", ["_build/daemon.py", "_build/config.json"])],
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
