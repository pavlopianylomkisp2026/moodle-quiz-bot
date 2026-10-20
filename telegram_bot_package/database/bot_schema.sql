-- Telegram bot schema for existing moodle_quiz.questions
-- Run this AFTER backing up the database.
--
-- Existing questions are assigned to Test 1.
-- Tests 2..22 are created as placeholders.

BEGIN;

CREATE TABLE IF NOT EXISTS tests (
    id SMALLSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    moodle_quiz_url TEXT
);

INSERT INTO tests (id, name, description)
VALUES
    (1, 'Тест 1', NULL),
    (2, 'Тест 2', NULL),
    (3, 'Тест 3', NULL),
    (4, 'Тест 4', NULL),
    (5, 'Тест 5', NULL),
    (6, 'Тест 6', NULL),
    (7, 'Тест 7', NULL),
    (8, 'Тест 8', NULL),
    (9, 'Тест 9', NULL),
    (10, 'Тест 10', NULL),
    (11, 'Тест 11', NULL),
    (12, 'Тест 12', NULL),
    (13, 'Тест 13', NULL),
    (14, 'Тест 14', NULL),
    (15, 'Тест 15', NULL),
    (16, 'Тест 16', NULL),
    (17, 'Тест 17', NULL),
    (18, 'Тест 18', NULL),
    (19, 'Тест 19', NULL),
    (20, 'Тест 20', NULL),
    (21, 'Тест 21', NULL),
    (22, 'Тест 22', NULL)
ON CONFLICT (id) DO NOTHING;

-- Keep SERIAL sequence above the highest explicit id.
SELECT setval(
    pg_get_serial_sequence('tests', 'id'),
    GREATEST((SELECT COALESCE(MAX(id), 1) FROM tests), 1),
    true
);

ALTER TABLE questions
    ADD COLUMN IF NOT EXISTS test_id SMALLINT REFERENCES tests(id);

-- All questions collected before this migration belong to Test 1.
UPDATE questions
SET test_id = 1
WHERE test_id IS NULL;

ALTER TABLE questions
    ALTER COLUMN test_id SET NOT NULL;

-- Before this migration question was globally unique.
-- The same question may legitimately exist in different tests.
ALTER TABLE questions
    DROP CONSTRAINT IF EXISTS questions_question_key;

ALTER TABLE questions
    DROP CONSTRAINT IF EXISTS questions_test_question_key;

ALTER TABLE questions
    ADD CONSTRAINT questions_test_question_key UNIQUE (test_id, question);

CREATE INDEX IF NOT EXISTS idx_questions_test_id
    ON questions(test_id);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL UNIQUE,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    attempts_total INTEGER NOT NULL DEFAULT 0 CHECK (attempts_total >= 0),
    attempts_used INTEGER NOT NULL DEFAULT 0 CHECK (attempts_used >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_attempts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    test_id SMALLINT NOT NULL REFERENCES tests(id),
    question_id BIGINT NOT NULL REFERENCES questions(id),
    used_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_attempts_user_id
    ON user_attempts(user_id);

CREATE INDEX IF NOT EXISTS idx_user_attempts_test_id
    ON user_attempts(test_id);

CREATE TABLE IF NOT EXISTS admin_actions (
    id BIGSERIAL PRIMARY KEY,
    admin_telegram_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    target_telegram_id BIGINT,
    test_id SMALLINT REFERENCES tests(id),
    amount INTEGER,
    details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_actions_created_at
    ON admin_actions(created_at);

COMMIT;
