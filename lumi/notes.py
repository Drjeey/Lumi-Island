import os
import threading

from .config import NOTES_PATH

# One lock for every writer (the notes panel, Lumi's add_to_note, the command bar's "note ..."), so an addition
# made while you type is never lost between a read and a write
_lock = threading.Lock()


def read():
    return NOTES_PATH.read_text(encoding='utf-8') if NOTES_PATH.exists() else ''


def _write(text):
    # Write a temporary file beside the note, then swap it in: an interrupted save leaves the old note whole
    tmp = NOTES_PATH.with_name(NOTES_PATH.name + '.tmp')
    NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, NOTES_PATH)


def save(text):
    """Replaces the note. Raises OSError if it couldn't be written."""
    with _lock:
        _write(text)


def append(line):
    """Adds a line to the end of the note and returns the whole note. Raises OSError if it couldn't be written."""
    with _lock:
        existing = read()
        text = (existing.rstrip('\n') + '\n' if existing.strip() else '') + line
        _write(text)
        return text
