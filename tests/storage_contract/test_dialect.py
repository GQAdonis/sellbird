"""The SQLite-to-Postgres rewrite, statement by statement (no database needed).

Expected strings are written by hand from the rules in
sellbird/storage_postgres/dialect.py, not captured from the code.
"""

import pytest

from sellbird.storage_postgres.dialect import (
    DialectError,
    is_read_only,
    keeps_rowid,
    split_statements,
    translate,
)


def pg(sql: str) -> str:
    return translate(sql, parametrized=True)


def test_placeholders_become_percent_s():
    assert pg("SELECT * FROM t WHERE a = ? AND b = ?") == \
        "SELECT * FROM t WHERE a = %s AND b = %s"


def test_percent_is_doubled_when_parameters_are_passed_even_inside_text():
    assert pg("SELECT 'a%' FROM t WHERE id = ?") == "SELECT 'a%%' FROM t WHERE id = %s"


def test_without_parameters_nothing_is_escaped():
    assert translate("SELECT 'a%' FROM t", parametrized=False) == "SELECT 'a%' FROM t"


def test_question_marks_inside_text_are_not_placeholders():
    assert translate("SELECT 'why?' FROM t", parametrized=False) == "SELECT 'why?' FROM t"


def test_a_placeholder_without_parameters_is_refused():
    with pytest.raises(DialectError):
        translate("SELECT * FROM t WHERE a = ?", parametrized=False)


def test_insert_or_ignore_becomes_on_conflict_do_nothing():
    assert pg("INSERT OR IGNORE INTO processed_replies (reply_id) VALUES (?)") == \
        "INSERT INTO processed_replies (reply_id) VALUES (%s) ON CONFLICT DO NOTHING"


def test_insert_or_replace_updates_every_listed_non_key_column():
    assert pg("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)") == (
        "INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, %s) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
        "updated_at = EXCLUDED.updated_at")


def test_insert_or_replace_into_an_unknown_table_is_refused():
    with pytest.raises(DialectError):
        pg("INSERT OR REPLACE INTO mystery (a) VALUES (?)")


@pytest.mark.parametrize("verb", ["ABORT", "FAIL", "ROLLBACK"])
def test_other_conflict_verbs_are_refused(verb):
    with pytest.raises(DialectError):
        pg(f"INSERT OR {verb} INTO settings (key) VALUES (?)")


def test_is_not_a_literal_is_null_safe_inequality():
    assert pg("UPDATE prospects SET status = ? WHERE id = ? AND status IS NOT 'opted_out'") == (
        "UPDATE prospects SET status = %s WHERE id = %s "
        "AND status IS DISTINCT FROM 'opted_out'")


def test_is_null_and_is_not_null_are_left_alone():
    assert pg("SELECT 1 FROM t WHERE a IS NULL AND b IS NOT NULL AND c = ?") == \
        "SELECT 1 FROM t WHERE a IS NULL AND b IS NOT NULL AND c = %s"


def test_scalar_max_and_min_become_greatest_and_least():
    assert translate("SELECT MAX(a, MIN(b, c)) FROM t", parametrized=False) == \
        "SELECT GREATEST(a, LEAST(b, c)) FROM t"


def test_aggregate_max_stays():
    assert translate("SELECT MAX(observed_at) FROM observations", parametrized=False) == \
        "SELECT MAX(observed_at) FROM observations"


def test_date_functions_are_renamed_to_the_compat_functions():
    assert pg("SELECT COUNT(*) FROM outbox WHERE date(sent_at) = date('now') AND kind = ?") == \
        "SELECT COUNT(*) FROM outbox WHERE sb_date(sent_at) = sb_date('now') AND kind = %s"
    assert pg("SELECT 1 FROM runs WHERE started_at < datetime('now', ?)") == \
        "SELECT 1 FROM runs WHERE started_at < sb_datetime('now', %s)"


def test_json_and_julianday_are_renamed():
    assert pg("SELECT 1 FROM settings s WHERE CASE WHEN json_valid(s.value) "
              "THEN julianday(json_extract(s.value, '$.checked_at')) END >= julianday(?)") == (
        "SELECT 1 FROM settings s WHERE CASE WHEN sb_json_valid(s.value) "
        "THEN sb_julianday(sb_json_extract(s.value, '$.checked_at')) END >= sb_julianday(%s)")


def test_instr_and_current_timestamp():
    assert translate("SELECT instr(email, '@'), CURRENT_TIMESTAMP FROM prospects",
                     parametrized=False) == \
        "SELECT strpos(email, '@'), sb_now() FROM prospects"


def test_a_column_called_date_is_not_a_function_call():
    sql = ("INSERT INTO usage_log (id, date, claude_calls) VALUES (?, ?, 1) "
           "ON CONFLICT(date) DO UPDATE SET claude_calls = usage_log.claude_calls + 1")
    assert pg(sql) == (
        "INSERT INTO usage_log (id, date, claude_calls) VALUES (%s, %s, 1) "
        "ON CONFLICT(date) DO UPDATE SET claude_calls = usage_log.claude_calls + 1")


def test_function_names_inside_text_are_untouched():
    assert translate("SELECT 'datetime(now) LIKE x' FROM t", parametrized=False) == \
        "SELECT 'datetime(now) LIKE x' FROM t"


def test_like_is_ascii_case_insensitive_as_in_sqlite():
    assert pg("SELECT 1 FROM outbox WHERE error LIKE ? AND body NOT LIKE ?") == \
        "SELECT 1 FROM outbox WHERE error ILIKE %s AND body NOT ILIKE %s"


def test_cast_as_real_is_double_precision():
    assert translate("SELECT CAST(score AS REAL) FROM prospects", parametrized=False) == \
        "SELECT CAST(score AS double precision) FROM prospects"


def test_order_by_sorts_nulls_first_ascending_and_last_descending():
    assert pg("SELECT * FROM outbox o ORDER BY send_at ASC, created_at ASC LIMIT ?") == \
        "SELECT * FROM outbox o ORDER BY send_at ASC NULLS FIRST, created_at ASC NULLS FIRST LIMIT %s"
    assert translate("SELECT id FROM t ORDER BY a DESC, b", parametrized=False) == \
        "SELECT id FROM t ORDER BY a DESC NULLS LAST, b NULLS FIRST"


def test_order_by_inside_a_subquery_ends_at_its_parenthesis():
    sql = ("SELECT 1 FROM observations o WHERE o.rowid = (SELECT n.rowid FROM observations n "
           "ORDER BY n.observed_at DESC, n.rowid DESC LIMIT 1)")
    assert translate(sql, parametrized=False) == (
        "SELECT 1 FROM observations o WHERE o.rowid = (SELECT n.rowid FROM observations n "
        "ORDER BY n.observed_at DESC NULLS LAST, n.rowid DESC NULLS LAST LIMIT 1)")


def test_scripts_split_on_semicolons_outside_text():
    assert split_statements("CREATE TABLE a (x text); INSERT INTO a VALUES ('x;y');") == [
        "CREATE TABLE a (x text)", "INSERT INTO a VALUES ('x;y')"]


def test_several_statements_with_parameters_are_refused():
    with pytest.raises(DialectError):
        pg("UPDATE t SET a = ?; UPDATE t SET b = ?")


@pytest.mark.parametrize("sql", [
    "SELECT * FROM t WHERE a GLOB ?",
    "SELECT * FROM t WHERE a = :name",
    "SELECT * FROM t WHERE a = ?1",
])
def test_unsupported_sqlite_syntax_fails_before_running(sql):
    with pytest.raises(DialectError):
        pg(sql)


def test_casts_are_not_mistaken_for_named_parameters():
    assert pg("SELECT value::text FROM settings WHERE key = ?") == \
        "SELECT value::text FROM settings WHERE key = %s"


@pytest.mark.parametrize("sql, expected", [
    ("SELECT * FROM observations", False),
    ("SELECT rowid, id FROM observations", True),
    ("SELECT id FROM actions ORDER BY created_at, rowid", False),
    ("WITH r AS (SELECT rowid FROM observations) SELECT id FROM r", False),
])
def test_rowid_is_kept_only_when_the_outer_select_names_it(sql, expected):
    assert keeps_rowid(sql) is expected


@pytest.mark.parametrize("sql, expected", [
    ("SELECT 1", True),
    ("  select * from t", True),
    ("WITH x AS (SELECT 1) SELECT * FROM x", True),
    ("UPDATE t SET a = 1", False),
    ("INSERT INTO t VALUES (1)", False),
    ("WITH x AS (SELECT 1) DELETE FROM t WHERE id IN (SELECT * FROM x)", False),
])
def test_read_only_statements_need_no_transaction(sql, expected):
    assert is_read_only(sql) is expected
