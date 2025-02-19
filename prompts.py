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

PRIORITY_ANALYSIS_PROMPT = """Analyser disse personene for rollen {role}.

Personer å vurdere:
{users}

For hver person, gjør en helhetlig vurdering basert på:

KRITISKE FAKTORER:
- LinkedIn-profil: Må ha en gyldig LinkedIn URL
- Rolle/tittel: Vurder hvor relevant nåværende rolle er for målrollen
- Data-kvalitet: Vurder confidence-score og mengde tilgjengelig informasjon

VURDERING:
- Gi en score fra 0.0 til 1.0 basert på hvor relevant personen er
- Høyere score til personer med sterke indikasjoner på match mot målrollen
- Lavere score til personer med manglende data eller uklar relevans
- Personer uten LinkedIn-profil skal automatisk få score 0.0

Returner de {max_results} mest relevante personene i JSON format:
{{
    "users": {{
        "person@eksempel.no": {{
            "score": 0.85,
            "reason": "Detaljert begrunnelse som inkluderer:
                      - Hvorfor rollen er relevant
                      - Kvaliteten på tilgjengelig data
                      - Andre relevante observasjoner"
        }}
    }}
}}

NB: 
- Prioriter kvalitet over kvantitet - velg kun de mest relevante kandidatene
- Begrunn tydelig hvorfor hver person ble valgt eller fikk høy score
- Skriv all begrunnelse på norsk
- Tenk på at disse personene skal analyseres videre via LinkedIn i neste steg
""" 