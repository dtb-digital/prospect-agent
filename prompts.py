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

VIKTIG: Returner kun et gyldig JSON-objekt som følger denne modellen:
{model_schema}

max_results: {max_results}
""" 