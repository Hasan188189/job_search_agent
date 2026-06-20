"""
Scorer
======
Lightweight keyword-based job match scorer.
Returns a float 0.0–1.0. Higher = better match.
The AI writer can optionally re-score with Claude for higher accuracy.
"""


def score_job(job: dict, profile: dict) -> float:
    """Score a job against the candidate profile using skill overlap."""
    candidate_skills = {s.lower() for s in profile.get("skills", [])}
    target_title = profile.get("target_title", "").lower()
    current_title = profile.get("current_title", "").lower()

    description = (
        job.get("description", "") + " " + job.get("title", "")
    ).lower()

    if not description.strip():
        return 0.5  # no info to score

    # Skill overlap score (0–0.6)
    matched_skills = sum(1 for skill in candidate_skills if skill in description)
    skill_score = min(matched_skills / max(len(candidate_skills), 1), 1.0) * 0.6

    # Title relevance score (0–0.3)
    title_score = 0.0
    job_title = job.get("title", "").lower()
    if any(word in job_title for word in target_title.split()):
        title_score += 0.2
    if any(word in job_title for word in current_title.split()):
        title_score += 0.1

    # Remote/location preference (0–0.1)
    pref = profile.get("preferred_work_type", "hybrid").lower()
    location_text = (job.get("location", "") + " " + description).lower()
    location_score = 0.0
    if pref == "remote" and ("remote" in location_text):
        location_score = 0.1
    elif pref == "hybrid" and ("hybrid" in location_text):
        location_score = 0.1
    elif pref == "onsite" and ("remote" not in location_text):
        location_score = 0.1

    total = round(skill_score + title_score + location_score, 2)
    return min(total, 1.0)
