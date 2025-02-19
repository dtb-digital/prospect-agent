from pydantic import BaseModel, Field
from typing import List, Dict

LINKEDIN_ANALYSIS_PROMPT = """Analyser denne LinkedIn profilen for rollen {role}.

Returner følgende felter i JSON format:
{{
    "summary": "En kort profesjonell oppsummering basert på all tilgjengelig data",
    "experience_years": 0,
    "current_company_years": 0.0,
    "key_skills": [],
    "leadership_experience": false,
    "education_level": "Velg én: Videregående, Bachelor, Master, PhD, eller Ukjent",
    "profile_type": "",
    "personality_traits": [
        {{"trait": "", "evidence": ""}}
    ],
    "career_pattern": {{
        "trajectory": "Oppadgående/Stabil/etc",
        "changes": "Hyppige/Sjeldne jobbskifter",
        "focus": "Hovedfokus i karrieren"
    }},
    "education_pattern": {{
        "focus": "Teknisk/Forretning/etc",
        "progression": "Pågående/Avsluttet",
        "relevance": "Høy/Medium/Lav"
    }},
    "network_strength": {{
        "followers": 0,
        "connections": 0,
        "engagement": "Høy/Medium/Lav"
    }},
    "fun_facts": []
}}

Profil data:
{linkedin_data}

NB: 
- Skriv all analyse på norsk
- Utdanningsnivå må være ett av følgende: Videregående, Bachelor, Master, PhD, eller Ukjent
- Antall år i nåværende bedrift skal rundes til nærmeste halve år
"""

PRIORITY_ANALYSIS_PROMPT = """Vurder disse personene for rollen {role}.

Personer å vurdere:
{users}

For hver person, gi en score fra 0 til 1 hvor:
- 0.0-0.2: Ikke relevant
- 0.3-0.5: Noe relevant erfaring
- 0.6-0.8: Veldig relevant
- 0.9-1.0: Perfekt match

Gi også en detaljert begrunnelse for hver score.

Returner svaret i JSON format med en "users" nøkkel som inneholder analysen:
{{
    "users": {{
        "person@eksempel.no": {{
            "score": 0.8,
            "reason": "Detaljert begrunnelse på norsk..."
        }}
    }}
}}

NB: Skriv all begrunnelse på norsk.
""" 