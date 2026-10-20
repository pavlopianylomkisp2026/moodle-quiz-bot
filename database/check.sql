SELECT COUNT(*) AS total_questions
FROM questions;

SELECT
    id,
    answer_letter,
    correct_answer,
    question,
    collected_at
FROM questions
ORDER BY id DESC
LIMIT 20;

-- Майбутній запит Telegram-бота:
-- SELECT correct_answer, answer_letter
-- FROM questions
-- WHERE question = %s;
