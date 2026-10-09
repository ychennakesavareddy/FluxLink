"""
FluxLink: Real-time lossless source-code and file transfer bridge CLI.
"""
from chennalink.app import ChennaLinkApp
from chennalink.__main__ import cli, CLI_HELP_TEXT

__version__ = "0.1.0"
__all__ = ["ChennaLinkApp", "cli", "CLI_HELP_TEXT", "__version__"]
