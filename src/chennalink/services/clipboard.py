import pyperclip

def copy_to_clipboard(text: str) -> bool:
    """
    Copies the given text to the clipboard exactly as is.
    Preserves all whitespace, newlines, tabs, etc.
    """
    try:
        pyperclip.copy(text)
        return True
    except Exception:
        return False
