"""
AI Writer
=========
Uses Claude to generate tailored cover letters and optionally
rewrite resume bullet points to match the job description.
"""

import os
import anthropic
from config.config_loader import load_config
from core.logger import get_logger

logger = get_logger("ai_writer")


class AIWriter:
    def __init__(self):
        cfg = load_config()
        api_key = cfg["ai"].get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = cfg["ai"].get("model", "claude-sonnet-4-6")
        self.tone = cfg["ai"].get("cover_letter_tone", "professional")

    def generate_cover_letter(self, job: dict, profile: dict) -> str:
        """Generate a tailored cover letter for a job."""
        prompt = self._build_prompt(job, profile)
        logger.info(f"✍️  Generating cover letter for {job['title']} @ {job['company']}")

        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    def score_fit(self, job: dict, profile: dict) -> float:
        """Ask Claude to rate how well the candidate fits the job (0.0–1.0)."""
        prompt = f"""Rate how well this candidate fits the job on a scale of 0 to 1.
Reply with ONLY a decimal number like 0.72 — nothing else.

JOB TITLE: {job.get('title')}
JOB DESCRIPTION (excerpt): {job.get('description', '')[:800]}

CANDIDATE:
- Title: {profile.get('current_title')}
- Years of experience: {profile.get('years_of_experience')}
- Skills: {', '.join(profile.get('skills', []))}
"""
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}],
            )
            return float(message.content[0].text.strip())
        except Exception:
            return 0.5

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_prompt(self, job: dict, profile: dict) -> str:
        tone_desc = {
            "professional": "formal and professional",
            "conversational": "friendly and conversational yet professional",
            "enthusiastic": "enthusiastic and energetic while staying professional",
        }.get(self.tone, "professional")

        return f"""Write a {tone_desc} cover letter for the following job application.

JOB DETAILS:
- Title: {job.get('title')}
- Company: {job.get('company')}
- Location: {job.get('location')}
- Description: {job.get('description', 'Not provided')[:1000]}

CANDIDATE PROFILE:
- Name: {profile.get('name')}
- Current Title: {profile.get('current_title')}
- Years of Experience: {profile.get('years_of_experience')}
- Key Skills: {', '.join(profile.get('skills', []))}
- Target Role: {profile.get('target_title')}

INSTRUCTIONS:
- Keep it to 3 paragraphs (opening, value proposition, closing)
- Highlight skills that match the job description
- Do NOT use generic filler phrases like "I am writing to express my interest"
- End with a clear call to action
- Do NOT include subject line, date, or address headers
- Output ONLY the cover letter body
"""
