from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup


@dataclass
class ParsedQuestion:
    question: str
    answer_letter: str
    correct_answer: str
    moodle_question_id: int | None


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_review_html(html: str) -> list[ParsedQuestion]:
    soup = BeautifulSoup(html, "html.parser")
    result: list[ParsedQuestion] = []

    for question_box in soup.select("div.que"):
        qtext_node = question_box.select_one(".qtext")
        rightanswer_node = question_box.select_one(".rightanswer")

        if not qtext_node or not rightanswer_node:
            continue

        # Не використовуємо get_text(" ", ...), бо glossary <a>
        # може розривати слово всередині питання.
        question = clean_text(qtext_node.get_text("", strip=False))

        rightanswer_raw = clean_text(rightanswer_node.get_text(" ", strip=True))
        prefix = "Правильна відповідь:"
        correct_answer = (
            rightanswer_raw.split(prefix, 1)[1].strip()
            if prefix in rightanswer_raw
            else rightanswer_raw
        )

        answer_letter = find_answer_letter(question_box, correct_answer)

        question_id = None
        hidden = question_box.select_one("input.questionflagpostdata")
        if hidden:
            value = hidden.get("value", "")
            match = re.search(r"qid=(\d+)", value)
            if match:
                question_id = int(match.group(1))

        if not answer_letter:
            raise ValueError(
                "Не вдалося визначити букву правильної відповіді: "
                f"{question[:120]}"
            )

        result.append(
            ParsedQuestion(
                question=question,
                answer_letter=answer_letter,
                correct_answer=correct_answer,
                moodle_question_id=question_id,
            )
        )

    return result


def find_answer_letter(question_box, correct_answer: str) -> str | None:
    for answer_box in question_box.select(".answer > div"):
        number = answer_box.select_one(".answernumber")
        text = answer_box.select_one(".flex-fill")

        if not number or not text:
            continue

        option_text = clean_text(text.get_text(" ", strip=True))
        if option_text == correct_answer:
            label = clean_text(number.get_text(" ", strip=True))
            match = re.match(
                r"([A-Za-zА-Яа-яЇїІіЄєҐґ0-9]+)\.", label
            )
            if match:
                return match.group(1)

    return None


def parse_review_file(path: str | Path) -> list[ParsedQuestion]:
    path = Path(path)
    return parse_review_html(path.read_text(encoding="utf-8"))
