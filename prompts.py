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

PRIORITY_ANALYSIS_PROMPT = """Analyser disse personene for å finne de som har rollen: {role}.

Personer å vurdere:
{users}

For hver person, gjør en helhetlig vurdering basert på:

KRITISKE FAKTORER:
- Rolle-match: Har personen en stilling/tittel som matcher målrollen vi leter etter?
- LinkedIn-profil: Må ha en gyldig LinkedIn URL for videre verifisering
- Data-kvalitet: Vurder confidence-score og mengde tilgjengelig informasjon

VURDERING:
- Gi en score fra 0.0 til 1.0 basert på hvor godt nåværende rolle matcher
- Høyere score til personer som har en rolle/tittel som direkte matcher det vi leter etter
- Lavere score til personer med roller som er uklare eller ikke relevante
- Personer uten LinkedIn-profil skal automatisk få score 0.0

Returner de {max_results} mest relevante personene i JSON format:
{{
    "users": {{
        "person@eksempel.no": {{
            "score": 0.85,
            "reason": "Detaljert begrunnelse som inkluderer:
                      - Hvorfor personens nåværende rolle matcher det vi leter etter
                      - Kvaliteten på tilgjengelig data
                      - Andre relevante observasjoner"
        }}
    }}
}}

NB: 
- Vi leter etter personer som HAR denne rollen nå, ikke potensielle kandidater
- Prioriter direkte rolle-match over andre faktorer
- Begrunn tydelig hvorfor hver persons nåværende rolle er relevant
- Skriv all begrunnelse på norsk
- Tenk på at disse personene skal analyseres videre via LinkedIn i neste steg
""" 