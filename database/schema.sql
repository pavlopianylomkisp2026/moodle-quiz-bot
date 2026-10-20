CREATE TABLE IF NOT EXISTS questions (
    id BIGSERIAL PRIMARY KEY,
    question TEXT NOT NULL UNIQUE,
    answer_letter VARCHAR(20) NOT NULL,
    correct_answer TEXT NOT NULL,
    moodle_question_id BIGINT,
    quiz_cmid BIGINT,
    source_attempt_id BIGINT,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_questions_question
    ON questions (question);

CREATE INDEX IF NOT EXISTS idx_questions_moodle_question_id
    ON questions (moodle_question_id);
