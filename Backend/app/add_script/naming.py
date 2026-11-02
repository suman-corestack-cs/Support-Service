import re


def _words(text):
    # Splits on anything that isn't a letter/digit — handles spaces,
    # underscores, hyphens, and CamelCase boundaries all at once.
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return [w for w in re.split(r"[^A-Za-z0-9]+", text) if w]


def slugify(text):
    """'Get EBS Snapshot Report' -> 'get-ebs-snapshot-report' (URL path segment)."""
    return "-".join(w.lower() for w in _words(text))


def snake_case(text):
    """'Get EBS Snapshot Report' -> 'get_ebs_snapshot_report' (Python identifier)."""
    return "_".join(w.lower() for w in _words(text))


def pascal_case(text):
    """'Get EBS Snapshot Report' -> 'GetEbsSnapshotReport' (class name)."""
    return "".join(w.capitalize() for w in _words(text))


def title_case_filename(text):
    """'Get EBS Snapshot Report' -> 'Get_Ebs_Snapshot_Report.py' — matches this
    codebase's existing (inconsistent but readable) script filename style."""
    return "_".join(w.capitalize() for w in _words(text)) + ".py"
