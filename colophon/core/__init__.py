"""What the server and the CLI share. Standard library only, so the CLI runs
on any machine's system python."""


class Invalid(ValueError):
    """Content that breaks the rules. The message is shown to the caller as is."""
