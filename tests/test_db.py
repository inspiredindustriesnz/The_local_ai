import sqlite3

from thelocalai.db import list_memory_keys


def test_list_memory_keys_filters_private_keys_only():
    con = sqlite3.connect(':memory:')
    con.execute('CREATE TABLE memory (key TEXT NOT NULL, value TEXT NOT NULL, created_at TEXT NOT NULL)')
    con.executemany(
        'INSERT INTO memory(key, value, created_at) VALUES (?, ?, ?)',
        [
            ('user_name', 'Ada', '2026-01-01T00:00:00Z'),
            ('dog_name', 'Mochi', '2026-01-01T00:00:00Z'),
            ('__last_topic', 'ai', '2026-01-01T00:00:00Z'),
        ],
    )

    keys = list_memory_keys(con)

    assert keys == ['dog_name', 'user_name']
