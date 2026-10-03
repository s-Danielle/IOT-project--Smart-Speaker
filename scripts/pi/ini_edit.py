"""A small, careful editor for INI files such as /etc/mopidy/mopidy.conf.

Python's configparser rewrites the whole file: it drops comments and changes
the layout. The live mopidy.conf holds the Spotify settings, so we change only
the lines we mean to change and leave every other byte alone.

Rules it understands:
  [section]            a header on its own line
  key = value          a key that starts in column 0 ("key: value" also works)
  key =                a list: the following indented lines are the items
      item one
      item two
  # comment / ; comment   left untouched
"""

import difflib
import re

_SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*$")
_KEY = re.compile(r"^([A-Za-z0-9_.\-]+)\s*[=:]\s*(.*)$")


def _is_comment(line):
    stripped = line.strip()
    return stripped.startswith("#") or stripped.startswith(";")


def _find_section(lines, name):
    """Return (header_index, end_index) of the first [name] block, or None."""
    wanted = name.strip().lower()
    start = None
    for index, line in enumerate(lines):
        match = _SECTION.match(line)
        if match:
            if start is not None:
                return start, index
            if match.group(1).strip().lower() == wanted:
                start = index
    if start is not None:
        return start, len(lines)
    return None


def _key_block(lines, first, end):
    """If lines[first] starts a key, return (key, value_lines, block_end)."""
    match = _KEY.match(lines[first])
    if not match or _is_comment(lines[first]):
        return None
    values = []
    if match.group(2).strip():
        values.append(match.group(2).strip())
    index = first + 1
    while index < end:
        line = lines[index]
        if line.strip() and line[0] in " \t" and not _is_comment(line):
            values.append(line.strip())
            index += 1
        else:
            break
    return match.group(1), values, index


def read_section(text, section):
    """Return {key: [value lines]} for one section ({} if it does not exist)."""
    lines = text.splitlines(keepends=True)
    found = _find_section(lines, section)
    if not found:
        return {}
    start, end = found
    result = {}
    index = start + 1
    while index < end:
        block = _key_block(lines, index, end)
        if block:
            key, values, index = block
            result[key] = values
        else:
            index += 1
    return result


def _render(key, values):
    values = [v for v in values if v != ""]
    if len(values) == 0:
        return ["%s =\n" % key]
    if len(values) == 1:
        return ["%s = %s\n" % (key, values[0])]
    return ["%s =\n" % key] + ["    %s\n" % v for v in values]


def set_values(text, section, values):
    """Return `text` with [section] keys set to `values` ({key: str or [str]}).

    Existing keys are replaced in place, missing keys are added at the end of
    the section, and a missing section is appended. Running it twice gives
    the same result.
    """
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    found = _find_section(lines, section)
    if not found:
        if lines and lines[-1].strip():
            lines.append("\n")
        elif not lines:
            pass
        lines.append("[%s]\n" % section)
        for key, value in values.items():
            items = value if isinstance(value, (list, tuple)) else [value]
            lines.extend(_render(key, list(items)))
        return "".join(lines)

    for key, value in values.items():
        items = list(value) if isinstance(value, (list, tuple)) else [value]
        start, end = _find_section(lines, section)
        replaced = False
        index = start + 1
        while index < end:
            block = _key_block(lines, index, end)
            if block and block[0].lower() == key.lower():
                _, _, block_end = block
                lines[index:block_end] = _render(key, items)
                replaced = True
                break
            index = block[2] if block else index + 1
        if not replaced:
            insert_at = end
            while insert_at > start + 1 and not lines[insert_at - 1].strip():
                insert_at -= 1
            lines[insert_at:insert_at] = _render(key, items)
    return "".join(lines)


def apply_sections(text, reference_text, sections):
    """Copy the given sections' keys from reference_text into text."""
    for section in sections:
        wanted = read_section(reference_text, section)
        if wanted:
            text = set_values(text, section, wanted)
    return text


def unified_diff(old, new, name, context=0):
    """A diff of old -> new. No context lines by default, so lines next to a
    change (which could be secrets in another section) are never printed."""
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=name + " (now)",
            tofile=name + " (after)",
            n=context,
        )
    )
