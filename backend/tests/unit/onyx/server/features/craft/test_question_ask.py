from onyx.server.features.build import question_ask


def test_questions_from_props_reads_option_labels() -> None:
    items = question_ask.questions_from_props(
        {
            "id": "que_1",
            "sessionID": "ses_1",
            "questions": [
                {
                    "header": "Modality",
                    "question": "Which modality?",
                    "options": [
                        {"label": "Oral", "description": "small molecule"},
                        {"label": "Injection", "description": "peptide"},
                    ],
                },
                {
                    "header": "Indication",
                    "question": "Which indication?",
                    "options": [{"label": "Obesity", "description": "weight"}],
                },
            ],
        }
    )
    assert [item.prompt for item in items] == ["Which modality?", "Which indication?"]
    assert items[0].options == ["Oral", "Injection"]
    assert items[1].options == ["Obesity"]


def test_prompt_and_options_uses_first_question() -> None:
    prompt, options = question_ask.prompt_and_options(
        {"questions": [{"question": "Pick one", "options": ["A", "B"]}]}
    )
    assert prompt == "Pick one"
    assert options == ["A", "B"]


def test_normalize_answers_prefers_matrix() -> None:
    assert question_ask.normalize_answers([["Oral"], ["Obesity"]], "ignored") == [
        ["Oral"],
        ["Obesity"],
    ]
    assert question_ask.normalize_answers(None, "Oral") == [["Oral"]]
    assert question_ask.normalize_answers(None, None) == []
