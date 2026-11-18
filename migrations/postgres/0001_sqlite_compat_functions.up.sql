-- SQLite's date and JSON functions, on the text Sellbird stores.
--
-- Sellbird keeps timestamps as ISO-8601 text in both backends ('2026-01-02
-- 03:04:05' from the database clock, '2026-01-02T03:04:05.123456' from
-- Python), in columns declared COLLATE "C" so they compare byte by byte, as
-- SQLite compares them. The stores' SQL is rewritten for Postgres by
-- sellbird/storage_postgres/dialect.py: CURRENT_TIMESTAMP becomes sb_now(),
-- datetime() sb_datetime(), and so on. These functions return exactly the text
-- SQLite would, so every comparison gives the same answer on both backends.
--
-- All times are UTC, as in SQLite. Unparseable input gives NULL, as in SQLite.
-- Known differences (none used by Sellbird): Julian-day numbers as input, the
-- 'localtime'/'unixepoch' modifiers, and month arithmetic past a month's end
-- (SQLite normalises 2026-01-31 +1 month to 2026-03-03; Postgres to 2026-02-28).

-- CURRENT_TIMESTAMP: 'YYYY-MM-DD HH:MM:SS', UTC, fixed for the statement.
CREATE FUNCTION sb_now() RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE
AS $$ SELECT pg_catalog.to_char(pg_catalog.timezone('UTC', pg_catalog.statement_timestamp()),
                                'YYYY-MM-DD HH24:MI:SS') $$;

-- An ISO-8601 time string as a UTC timestamp, or NULL. Accepts what SQLite
-- does: 'YYYY-MM-DD', optionally ' HH:MM', ':SS', '.fraction', with 'T' or a
-- space, and an optional 'Z' or '+HH:MM' offset (converted to UTC).
CREATE FUNCTION sb_parse_time(value text) RETURNS timestamp
LANGUAGE plpgsql STABLE STRICT PARALLEL SAFE
AS $$
DECLARE
    v text := pg_catalog.btrim(value);
BEGIN
    IF lower(v) = 'now' THEN
        RETURN pg_catalog.timezone('UTC', pg_catalog.statement_timestamp());
    END IF;
    IF v !~ '^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(\s*(Z|[+-]\d{2}:?\d{2}))?)?$' THEN
        RETURN NULL;
    END IF;
    v := pg_catalog.replace(v, 'T', ' ');
    IF v ~ '^\S+ \S+?\s*(Z|[+-]\d{2}:?\d{2})$' THEN
        RETURN (v::timestamptz) AT TIME ZONE 'UTC';
    END IF;
    RETURN v::timestamp;
EXCEPTION
    WHEN invalid_datetime_format OR datetime_field_overflow OR invalid_parameter_value THEN
        RETURN NULL;
END
$$;

-- SQLite's modifiers: '+N days' (also hours, minutes, seconds, months, years,
-- singular or plural, fractions allowed) and 'start of day|month|year'.
-- Anything else gives NULL, as SQLite does for a modifier it doesn't know.
CREATE FUNCTION sb_apply_modifiers(ts timestamp, mods text[]) RETURNS timestamp
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE
AS $$
DECLARE
    m text;
BEGIN
    IF ts IS NULL OR mods IS NULL THEN
        RETURN ts;
    END IF;
    FOREACH m IN ARRAY mods LOOP
        IF m IS NULL THEN
            RETURN NULL;
        END IF;
        m := lower(pg_catalog.btrim(m));
        IF m ~ '^[+-]?\d+(\.\d+)?\s+(second|minute|hour|day|month|year)s?$' THEN
            ts := ts + pg_catalog.ltrim(m, '+')::interval;
        ELSIF m = 'start of day' THEN
            ts := pg_catalog.date_trunc('day', ts);
        ELSIF m = 'start of month' THEN
            ts := pg_catalog.date_trunc('month', ts);
        ELSIF m = 'start of year' THEN
            ts := pg_catalog.date_trunc('year', ts);
        ELSE
            RETURN NULL;
        END IF;
    END LOOP;
    RETURN ts;
END
$$;

-- datetime(value [, modifier ...]): 'YYYY-MM-DD HH:MM:SS' or NULL.
CREATE FUNCTION sb_datetime(value text) RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE
AS $$ SELECT pg_catalog.to_char(sb_parse_time(value), 'YYYY-MM-DD HH24:MI:SS') $$;

CREATE FUNCTION sb_datetime(value text, VARIADIC mods text[]) RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE
AS $$ SELECT pg_catalog.to_char(sb_apply_modifiers(sb_parse_time(value), mods),
                                'YYYY-MM-DD HH24:MI:SS') $$;

-- date(value [, modifier ...]): 'YYYY-MM-DD' or NULL.
CREATE FUNCTION sb_date(value text) RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE
AS $$ SELECT pg_catalog.to_char(sb_parse_time(value), 'YYYY-MM-DD') $$;

CREATE FUNCTION sb_date(value text, VARIADIC mods text[]) RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE
AS $$ SELECT pg_catalog.to_char(sb_apply_modifiers(sb_parse_time(value), mods), 'YYYY-MM-DD') $$;

-- julianday(value [, modifier ...]): days since noon, 24 November 4714 BC (UTC).
CREATE FUNCTION sb_julianday(value text) RETURNS double precision
LANGUAGE sql STABLE PARALLEL SAFE
AS $$ SELECT pg_catalog.date_part('epoch', sb_parse_time(value)) / 86400.0 + 2440587.5 $$;

CREATE FUNCTION sb_julianday(value text, VARIADIC mods text[]) RETURNS double precision
LANGUAGE sql STABLE PARALLEL SAFE
AS $$ SELECT pg_catalog.date_part('epoch', sb_apply_modifiers(sb_parse_time(value), mods))
             / 86400.0 + 2440587.5 $$;

-- json_valid(text): whether it is well-formed JSON (boolean; SQLite's 1/0).
CREATE FUNCTION sb_json_valid(value text) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT value IS JSON $$;

-- A SQLite JSON path ('$', '$.a.b', '$."a.b"', '$.list[0]') as a jsonb path
-- array, or NULL for a path this doesn't support.
CREATE FUNCTION sb_json_path(path text) RETURNS text[]
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE
AS $$
DECLARE
    rest text;
    keys text[] := '{}';
    m text[];
BEGIN
    IF left(path, 1) <> '$' THEN
        RETURN NULL;
    END IF;
    rest := substr(path, 2);
    WHILE rest <> '' LOOP
        m := regexp_match(rest, '^\."([^"]*)"');
        IF m IS NOT NULL THEN
            keys := keys || m[1];
            rest := substr(rest, length(m[1]) + 4);
            CONTINUE;
        END IF;
        m := regexp_match(rest, '^\.([^.\[]+)');
        IF m IS NOT NULL THEN
            keys := keys || m[1];
            rest := substr(rest, length(m[1]) + 2);
            CONTINUE;
        END IF;
        m := regexp_match(rest, '^\[(\d+)\]');
        IF m IS NOT NULL THEN
            keys := keys || m[1];
            rest := substr(rest, length(m[1]) + 3);
            CONTINUE;
        END IF;
        RETURN NULL;
    END LOOP;
    RETURN keys;
END
$$;

-- json_extract(doc, path) as SQLite returns it, as text: a string's value, a
-- number's digits, 1/0 for true/false, NULL for null or a missing path, and
-- JSON text for an object or array. Malformed JSON gives NULL rather than an
-- error, so a json_valid() guard holds whatever order Postgres evaluates the
-- conditions of a WHERE clause in.
CREATE FUNCTION sb_json_extract(doc text, path text) RETURNS text
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE
AS $$
DECLARE
    keys text[];
    found jsonb;
BEGIN
    IF doc IS NULL OR path IS NULL OR NOT (doc IS JSON) THEN
        RETURN NULL;
    END IF;
    keys := sb_json_path(path);
    IF keys IS NULL THEN
        RETURN NULL;
    END IF;
    found := doc::jsonb #> keys;
    IF found IS NULL THEN
        RETURN NULL;
    END IF;
    CASE jsonb_typeof(found)
        WHEN 'null' THEN RETURN NULL;
        WHEN 'string' THEN RETURN found #>> '{}';
        WHEN 'boolean' THEN RETURN CASE WHEN found = 'true'::jsonb THEN '1' ELSE '0' END;
        ELSE RETURN found::text;
    END CASE;
END
$$;
