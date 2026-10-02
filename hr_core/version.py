"""The product's version and the version of the data it writes (phase 2.5).

VERSION is what a person sees and what the installer carries. DATA_VERSION changes only when the shape of what is
kept in the data folder changes; hr_core/upgrade.py moves older data forward, step by step, after a verified
pre-update backup, and refuses data written by a newer program.
"""

PRODUCT = "HR-System"
VERSION = "1.0.0"
DATA_VERSION = 6
DEVELOPER = "Mohamed Fawzy"
COPYRIGHT = "(c) 2026 Mohamed Fawzy"
