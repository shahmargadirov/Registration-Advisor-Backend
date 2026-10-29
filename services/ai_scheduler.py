import json
import os

from services.schedule_logic.conflicts import  has_time_conflict
from services.schedule_logic.ai_helpers import compact_candidate
from utils.normalize import normalize


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI
    except ImportError:
        return None

    return OpenAI(api_key=api_key)


def choose_schedule_with_ai(student_profile, candidates, max_classes=5):
    client = get_openai_client()
    if client is None:
        return []

    compact_candidates = [compact_candidate(c) for c in candidates]

    system_prompt = """
You are a strict academic scheduling assistant.

You must follow these rules:
1. Only select from the provided candidates.
2. Prefer major requirements first.
3. Use UCC only when needed after major requirements.
4. Only choose one course for a single-slot option group.
5. Only choose one science sequence at a time unless the student already completed the full sequence.
6. Never recommend a class with a time conflict against another recommended class.
7. Never recommend a class if prerequisites are not satisfied.
8. Never recommend a class if restrictions are not satisfied.
9. Never recommend a class already completed or already in progress.
10. Return valid JSON only.
"""

    user_prompt = f"""
Build a next-semester recommendation for this student.

Scheduling priorities:
1. Recommend exactly {max_classes} classes when at least {max_classes} valid candidates exist.
2. Major requirements come first.
3. Use UCC only if there is still room after major requirements.
4. Do not invent CRNs, titles, or course codes.

Student profile:
{json.dumps(student_profile, indent=2)}

Valid candidates:
{json.dumps(compact_candidates, indent=2)}

Return exactly this JSON shape:
{{
  "recommended_crns": ["12345", "67890", "11111", "22222", "33333"],
  "reasoning": [
    "major requirements were prioritized first"
  ]
}}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = response.choices[0].message.content.strip()

    try:
        parsed = json.loads(content)
        recommended_crns = [str(crn) for crn in parsed.get("recommended_crns", [])]
    except Exception:
        recommended_crns = []

    selected = []
    seen_codes = set()

    for recommended_crn in recommended_crns:
        matching_candidate = next(
            (
                candidate for candidate in candidates
                if str(candidate["section"]["crn"]) == recommended_crn
            ),
            None,
        )

        if not matching_candidate:
            continue

        code = normalize(matching_candidate["section"]["course_code"])

        if code in seen_codes:
            continue

        if any(has_time_conflict(matching_candidate["section"], picked["section"]) for picked in selected):
            continue

        selected.append(matching_candidate)
        seen_codes.add(code)

        if len(selected) == max_classes:
            break

    return selected
