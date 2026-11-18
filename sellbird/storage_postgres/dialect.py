"""Turn the SQLite-dialect SQL Sellbird's stores write into Postgres SQL.

The stores keep one code path: they write SQLite SQL with ``?`` placeholders,
and this module rewrites each statement for Postgres just before it runs. The
rewrite is deliberately small and mechanical. Everything SQLite has that
Postgres spells differently is handled in one of two places:

Here, as text (string literals, quoted identifiers and comments are never
touched):

=====================================  =========================================
SQLite                                  Postgres
=====================================  =========================================
``?`` placeholders                      ``%s`` (and a literal ``%`` as ``%%``)
``INSERT OR IGNORE INTO t ...``         ``INSERT INTO t ... ON CONFLICT DO NOTHING``
``INSERT OR REPLACE INTO t (cols) ...`` ``... ON CONFLICT (pk) DO UPDATE SET``
                                        every other listed column
``x IS NOT 'v'`` / ``x IS 'v'``         ``IS DISTINCT FROM`` / ``IS NOT DISTINCT FROM``
scalar ``MAX(a, b)`` / ``MIN(a, b)``    ``GREATEST(a, b)`` / ``LEAST(a, b)``
``LIKE`` (ASCII case-insensitive)       ``ILIKE`` (columns are ``COLLATE "C"``,
                                        so only ASCII folds, as in SQLite)
``CURRENT_TIMESTAMP``                   ``sb_now()``
``datetime(...)``, ``date(...)``,       ``sb_datetime(...)``, ``sb_date(...)``,
``julianday(...)``                      ``sb_julianday(...)``
``json_extract``, ``json_valid``        ``sb_json_extract``, ``sb_json_valid``
``instr(a, b)``, ``ifnull(a, b)``       ``strpos(a, b)``, ``coalesce(a, b)``
``CAST(x AS REAL)``                     ``CAST(x AS double precision)``
``ORDER BY x`` / ``ORDER BY x DESC``    ``... NULLS FIRST`` / ``... NULLS LAST``
                                        (SQLite sorts NULL before every value)
=====================================  =========================================

In the database, as functions created by migration 0001
(``migrations/postgres/0001_sqlite_compat_functions.up.sql``): the ``sb_*``
functions reproduce SQLite's date and JSON functions on the same ISO-8601
text Sellbird stores, so comparisons give the same answers on both backends.

``rowid`` needs no rewrite: every Postgres table has a ``rowid`` identity
column, and the connection hides it from results unless the outermost select
list names it, as SQLite's ``SELECT *`` never includes it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Primary keys, for INSERT OR REPLACE. Every table Sellbird has.
PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "actions": ("id",),
    "campaign_mailboxes": ("campaign_id", "mailbox_id"),
    "campaigns": ("id",),
    "companies": ("id",),
    "conversations": ("id",),
    "email_patterns": ("domain",),
    "feedback": ("id",),
    "mailboxes": ("id",),
    "observations": ("id",),
    "outbox": ("id",),
    "processed_replies": ("reply_id",),
    "prospects": ("id",),
    "runs": ("id",),
    "settings": ("key",),
    "signal_codes": ("code",),
    "suppressions": ("id",),
    "usage_events": ("id",),
    "usage_log": ("id",),
}

_STR, _IDENT = "\x01", "\x02"
_MASK = re.compile(r"([\x01\x02])(\d+)\1")

_FUNCTIONS = [
    (re.compile(r"(?<![\w.$])datetime\s*\(", re.I), "sb_datetime("),
    (re.compile(r"(?<![\w.$])date\s*\(", re.I), "sb_date("),
    (re.compile(r"(?<![\w.$])julianday\s*\(", re.I), "sb_julianday("),
    (re.compile(r"(?<![\w.$])json_extract\s*\(", re.I), "sb_json_extract("),
    (re.compile(r"(?<![\w.$])json_valid\s*\(", re.I), "sb_json_valid("),
    (re.compile(r"(?<![\w.$])instr\s*\(", re.I), "strpos("),
    (re.compile(r"(?<![\w.$])ifnull\s*\(", re.I), "coalesce("),
]
_REWRITES = [
    (re.compile(r"\bCURRENT_TIMESTAMP\b", re.I), "sb_now()"),
    (re.compile(r"\bCURRENT_DATE\b", re.I), "sb_date('now')"),
    (re.compile(r"\bAS\s+REAL\b", re.I), "AS double precision"),
    (re.compile(r"(?<![\w.])LIKE\b", re.I), "ILIKE"),
    # x IS NOT 'v' / x IS ? -> null-safe comparisons (before the plain IS form).
    (re.compile(r"\bIS\s+NOT\s+(?=\x01|\?)", re.I), "IS DISTINCT FROM "),
    (re.compile(r"\bIS\s+(?=\x01|\?)", re.I), "IS NOT DISTINCT FROM "),
]
_INSERT_OR = re.compile(
    r"^\s*(?:INSERT\s+OR\s+(IGNORE|REPLACE|ABORT|FAIL|ROLLBACK)|(REPLACE))\s+INTO\s+",
    re.I,
)
_TABLE_AND_COLUMNS = re.compile(r"^([A-Za-z_]\w*)\s*\(([^()]*)\)")
_MINMAX = re.compile(r"(?<![\w.])(MAX|MIN)\s*\(", re.I)
_UNSUPPORTED = re.compile(r"\bGLOB\b|\bPRAGMA\b|\?\d+|(?<![:\w]):[A-Za-z_]\w*", re.I)
_READ_ONLY_START = re.compile(r"^\s*(SELECT|VALUES|SHOW|EXPLAIN)\b", re.I)
_WRITE_WORD = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE)\b", re.I)


class DialectError(ValueError):
    """SQL this layer can't carry to Postgres. Raised before anything runs."""


@dataclass(frozen=True)
class _Masked:
    """A statement with its literals, quoted identifiers and comments taken out."""

    text: str
    pieces: tuple[str, ...]


def _mask(sql: str) -> _Masked:
    out: list[str] = []
    pieces: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in ("'", '"'):
            j = i + 1
            while j < n:
                if sql[j] == ch:
                    if j + 1 < n and sql[j + 1] == ch:  # doubled quote = escaped
                        j += 2
                        continue
                    break
                j += 1
            if j >= n:
                raise DialectError("unterminated quoted text in SQL")
            pieces.append(sql[i:j + 1])
            tag = _STR if ch == "'" else _IDENT
            out.append(f"{tag}{len(pieces) - 1}{tag}")
            i = j + 1
        elif sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j
            out.append(" ")
        elif sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            if j < 0:
                raise DialectError("unterminated comment in SQL")
            i = j + 2
            out.append(" ")
        else:
            out.append(ch)
            i += 1
    return _Masked("".join(out), tuple(pieces))


def _unmask(text: str, pieces: tuple[str, ...], *, parametrized: bool) -> str:
    def put_back(m: re.Match) -> str:
        piece = pieces[int(m.group(2))]
        return piece.replace("%", "%%") if parametrized else piece
    return _MASK.sub(put_back, text)


def split_statements(sql: str) -> list[str]:
    """The statements of a script, split on top-level semicolons."""
    masked = _mask(sql)
    statements = []
    for part in masked.text.split(";"):
        if part.strip():
            statements.append(_unmask(part, masked.pieces, parametrized=False).strip())
    return statements


def _closing_paren(text: str, open_at: int) -> int:
    depth = 0
    for k in range(open_at, len(text)):
        if text[k] == "(":
            depth += 1
        elif text[k] == ")":
            depth -= 1
            if depth == 0:
                return k
    raise DialectError("unbalanced parentheses in SQL")


def _scalar_minmax(text: str) -> str:
    """MAX(a, b) -> GREATEST(a, b); MIN(a, b) -> LEAST(a, b). Aggregates stay."""
    pos = 0
    while True:
        m = _MINMAX.search(text, pos)
        if not m:
            return text
        open_at = m.end() - 1
        close_at = _closing_paren(text, open_at)
        depth, scalar = 0, False
        for ch in text[open_at + 1:close_at]:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                scalar = True
                break
        if scalar:
            name = "GREATEST" if m.group(1).upper() == "MAX" else "LEAST"
            text = text[:m.start()] + name + "(" + text[open_at + 1:]
            pos = m.start() + len(name)
        else:
            pos = m.end()


def _depth0(text: str) -> str:
    """The text with everything inside parentheses blanked out."""
    out, depth = [], 0
    for ch in text:
        if ch == "(":
            depth += 1
            out.append(" ")
        elif ch == ")":
            depth = max(0, depth - 1)
            out.append(" ")
        else:
            out.append(ch if depth == 0 else " ")
    return "".join(out)


_ORDER_BY = re.compile(r"\bORDER\s+BY\b", re.I)
_CLAUSE_END = re.compile(r"\b(LIMIT|OFFSET|UNION|INTERSECT|EXCEPT|FOR|FETCH|WINDOW)\b", re.I)
_HAS_NULLS = re.compile(r"\bNULLS\s+(FIRST|LAST)\s*$", re.I)
_IS_DESC = re.compile(r"\bDESC\s*$", re.I)


def _order_item(item: str) -> str:
    body = item.rstrip()
    tail = item[len(body):]
    if not body.strip() or _HAS_NULLS.search(body):
        return item
    return body + (" NULLS LAST" if _IS_DESC.search(body) else " NULLS FIRST") + tail


def _sqlite_null_order(text: str) -> str:
    """SQLite sorts NULL before every value; Postgres after. Say which, per item."""
    pos = 0
    while True:
        m = _ORDER_BY.search(text, pos)
        if not m:
            return text
        start = m.end()
        depth, end, k = 0, len(text), start
        while k < len(text):
            ch = text[k]
            if ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    end = k
                    break
                depth -= 1
            elif depth == 0:
                stop = _CLAUSE_END.match(text, k)
                if stop and (k == 0 or not (text[k - 1].isalnum() or text[k - 1] == "_")):
                    end = k
                    break
            k += 1
        items, depth, last = [], 0, start
        for j in range(start, end):
            ch = text[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                items.append(text[last:j])
                last = j + 1
        items.append(text[last:end])
        clause = ",".join(_order_item(i) for i in items)
        text = text[:start] + clause + text[end:]
        pos = start + len(clause)


def _insert_before_returning(text: str, clause: str) -> str:
    top = _depth0(text)
    m = re.search(r"\bRETURNING\b", top, re.I)
    if m:
        return text[:m.start()].rstrip() + " " + clause + " " + text[m.start():]
    return text.rstrip() + " " + clause


def _insert_or(text: str) -> str:
    m = _INSERT_OR.match(text)
    if not m:
        return text
    verb = (m.group(1) or m.group(2)).upper()
    if verb not in ("IGNORE", "REPLACE"):
        raise DialectError(f"INSERT OR {verb} has no Postgres form here")
    if re.search(r"\bON\s+CONFLICT\b", _depth0(text), re.I):
        raise DialectError(f"INSERT OR {verb} cannot be combined with ON CONFLICT")
    rest = text[m.end():]
    body = "INSERT INTO " + rest
    if verb == "IGNORE":
        return _insert_before_returning(body, "ON CONFLICT DO NOTHING")
    cols = _TABLE_AND_COLUMNS.match(rest)
    if not cols:
        raise DialectError("INSERT OR REPLACE needs an explicit column list")
    table = cols.group(1).lower()
    keys = PRIMARY_KEYS.get(table)
    if keys is None:
        raise DialectError(f"INSERT OR REPLACE into unknown table {table!r}")
    listed = [c.strip() for c in cols.group(2).split(",") if c.strip()]
    others = [c for c in listed if c.lower() not in keys]
    target = ", ".join(keys)
    if not others:
        clause = f"ON CONFLICT ({target}) DO NOTHING"
    else:
        sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in others)
        clause = f"ON CONFLICT ({target}) DO UPDATE SET {sets}"
    return _insert_before_returning(body, clause)


def translate_statement(sql: str, *, parametrized: bool) -> str:
    """One SQLite statement as Postgres SQL. ``parametrized``: parameters will
    be passed, so ``?`` becomes ``%s`` and a literal ``%`` becomes ``%%``."""
    masked = _mask(sql)
    text = masked.text
    bad = _UNSUPPORTED.search(text)
    if bad:
        raise DialectError(f"unsupported SQLite syntax for Postgres: {bad.group(0)!r}")
    text = _insert_or(text)
    for pattern, replacement in _FUNCTIONS:
        text = pattern.sub(replacement, text)
    for pattern, replacement in _REWRITES:
        text = pattern.sub(replacement, text)
    text = _scalar_minmax(text)
    text = _sqlite_null_order(text)
    if parametrized:
        text = text.replace("%", "%%").replace("?", "%s")
    elif "?" in text:
        raise DialectError("SQL has ? placeholders but no parameters were given")
    return _unmask(text, masked.pieces, parametrized=parametrized).strip()


def translate(sql: str, *, parametrized: bool) -> str:
    """SQLite SQL (one statement, or a script of several) as Postgres SQL."""
    statements = split_statements(sql)
    if parametrized and len(statements) > 1:
        raise DialectError("one statement at a time when passing parameters")
    return ";\n".join(translate_statement(s, parametrized=parametrized) for s in statements)


def is_read_only(sql: str) -> bool:
    """True for a statement that only reads (so needs no transaction, as in sqlite3)."""
    masked = _mask(sql).text
    if _READ_ONLY_START.match(masked):
        return True
    if re.match(r"^\s*WITH\b", masked, re.I):
        return not _WRITE_WORD.search(_depth0(masked))
    return False


def keeps_rowid(sql: str) -> bool:
    """Whether the outermost select list names ``rowid`` (else results hide it)."""
    top = _depth0(_mask(sql).text)
    select = re.search(r"\bSELECT\b", top, re.I)
    if not select:
        return False
    after = top[select.end():]
    frm = re.search(r"\bFROM\b", after, re.I)
    select_list = after[:frm.start()] if frm else after
    return re.search(r"\browid\b", select_list, re.I) is not None


def first_word(sql: str) -> str:
    """The statement's first keyword, upper-cased ("" for an empty statement)."""
    m = re.match(r"^\s*([A-Za-z]+)", _mask(sql).text)
    return m.group(1).upper() if m else ""
