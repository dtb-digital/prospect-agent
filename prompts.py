from typing import Type, Dict, Any
import json
from pydantic import BaseModel
from models import (
    User, BasicInfo, CareerInfo, ExpertiseInfo, 
    EducationInfo, NetworkInfo, PersonalityInfo, MetaInfo
)

def get_model_schema(model_class: Type[BaseModel]) -> str:
    """Henter JSON schema for en modell i lesbart format"""
    schema = model_class.model_json_schema()
    return json.dumps(schema, indent=2, ensure_ascii=False)

def get_nested_field_descriptions(model_class: Type[BaseModel]) -> str:
    """Henter feltbeskrivelser for en modell med sub-modeller"""
    descriptions = []
    for field_name, field_info in model_class.model_fields.items():
        if hasattr(field_info.annotation, 'model_fields'):
            descriptions.append(f"\n{field_name.upper()}:")
            sub_model = field_info.annotation
            for sub_field, sub_info in sub_model.model_fields.items():
                desc = sub_info.description or "Ingen beskrivelse tilgjengelig"
                descriptions.append(f"- {sub_field}: {desc}")
        else:
            desc = field_info.description or "Ingen beskrivelse tilgjengelig"
            descriptions.append(f"- {field_name}: {desc}")
    return "\n".join(descriptions)

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

PRIORITERINGSKRITERIER:
- Beslutningsmyndighet og innflytelse
- Match mot målrollen/produktet
- Timing og tilgjengelighet
- Datakvalitet og aktualitet

VIKTIG: Returner kun et gyldig JSON-objekt som følger denne modellen:
{model_schema}

max_results: {max_results}
""" 