from typing import Type, Dict, Any
import json
from pydantic import BaseModel

def get_model_schema(model_class: Type[BaseModel]) -> str:
    """Henter JSON schema for en modell i lesbart format"""
    schema = model_class.model_json_schema()
    return json.dumps(schema, indent=2, ensure_ascii=False)

def validate_llm_output(output: str, model_class: Type[BaseModel]) -> Dict[str, Any]:
    """Validerer og konverterer LLM output mot modell"""
    try:
        data = json.loads(output)
        validated = model_class(**data)
        return validated.model_dump()
    except Exception as e:
        raise ValueError(f"Ugyldig output format: {str(e)}")

ANALYSIS_PROMPT = """
Utfør en komplett analyse av denne profilen med fokus på B2B-salgspotensial.

PROFIL:
{raw_profile}

MÅLROLLE/PRODUKT:
{target_role}

ANALYSEMETODE:
- Utfør dyp analyse av både eksplisitt og implisitt informasjon:
  * Analyser all tilgjengelig data systematisk
  * Se etter mønstre og sammenhenger
  * Unngå forhastede konklusjoner
  * Bruk all tilgjengelig data som innsikt. Hvordan folk ordlegger seg, hva de fokuserer på, hvordan de legger frem sine erfaringer etc kan si mye om en person

- Fokuser på fakta og observasjoner:
  * Skill mellom faktiske data og antakelser
  * Dokumenter kilder til konklusjoner
  * Vær presis i beskrivelser

- Vær objektiv i analysen:
  * Unngå forutinntatte meninger
  * Balanser positive og negative observasjoner
  * Vurder alternative perspektiver

- Følg datamodellen nøye:
  * Fyll ut alle relevante felter basert på tilgjengelig data
  * Marker tydelig når data mangler
  * Sikre at all output følger spesifisert schema

OUTPUT FORMAT:
VIKTIG: Returner kun et gyldig JSON-objekt som følger denne modellen:
{model_schema}

"""

PRIORITY_PROMPT = """
Evaluer og prioriter disse prospektene for {target_role}.

PROSPEKTER:
{prospects}

TILGJENGELIG DATA:
{available_data}

PRIORITERINGSKRITERIER:
- Match mot målrollen/produktet
- Datakvalitet og aktualitet
- Ved flere relevante prospekter, prioriter prospekter med høyest sannsynlighet for salg
- Beslutningsmyndighet og innflytelse kan være bra, men kan også skape barrierer for salg
- Påvirkere og brukere kan ofte være gode for å komme inn under radaren for å påvirke beslutningen

VIKTIG: Returner kun et gyldig JSON-objekt som følger denne modellen:
{model_schema}

max_results: {max_results}
""" 