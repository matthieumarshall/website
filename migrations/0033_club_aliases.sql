-- Imported club names are identities only when staff have linked them to a club.
CREATE SEQUENCE IF NOT EXISTS club_alias_id_seq START 1;
CREATE TABLE IF NOT EXISTS club_aliases (
    id INTEGER PRIMARY KEY DEFAULT nextval('club_alias_id_seq'),
    -- DuckDB rejects updates to referenced clubs for some non-key changes.
    -- The service validates this relationship before writing an alias.
    club_id INTEGER NOT NULL,
    name VARCHAR NOT NULL
);

-- Known names observed in production, only where the club name is unambiguous.
INSERT INTO club_aliases (club_id, name)
SELECT min(c.id), known.alias
FROM (VALUES
    ('Abingdon Athletics Club', 'Abingdon AC'),
    ('Banbury Harriers Athletic Club', 'Banbury harriers AC'),
    ('Headington Road Runners', 'Headington RR'),
    ('Highworth Running Club', 'Highworth RC'),
    ('Radley AC', 'Radley Athletic Club'),
    ('Team Kennet Triathlon & AC', 'Team Kennet Tri')
) AS known(club_name, alias)
JOIN clubs c ON lower(trim(c.name)) = lower(trim(known.club_name))
GROUP BY known.alias
HAVING count(*) = 1;
