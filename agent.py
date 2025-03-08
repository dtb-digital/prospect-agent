from typing import Annotated, List, Dict, Union, TypedDict, Any, Optional, Type
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import START, END, StateGraph
from langchain_core.runnables import RunnableConfig
from langsmith import traceable
from langsmith.wrappers import wrap_openai
from openai import OpenAI
import json
import os
from dotenv import load_dotenv
from pydantic import BaseModel
from tools import linkedin_tool, hunter_tool, assert_person_in_attio, create_note_in_attio, get_attio_person_schema, get_attio_note_schema
from models import (
    SearchConfig, 
    PriorityAnalysis,
    HunterResponse,
    User,
    State,
    merge_users,
)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from system_prompts import get_analysis_prompt, get_priority_prompt
from prompt_hub import get_prompt_from_hub

load_dotenv()

def get_model_schema(model_class: Type[BaseModel]) -> str:
    """Henter JSON schema for en modell i lesbart format"""
    schema = model_class.model_json_schema()
    return json.dumps(schema, indent=2, ensure_ascii=False)

# Configs
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0

# Wrap OpenAI client for better tracing
openai_client = wrap_openai(OpenAI())

# Initialiser LLM
llm = ChatOpenAI(
    model_name=os.getenv("MODEL_NAME", DEFAULT_MODEL),
    temperature=float(os.getenv("TEMPERATURE", DEFAULT_TEMPERATURE))
)

# Hent prompter fra LangSmith
analysis_prompt = get_analysis_prompt()
priority_prompt = get_priority_prompt()

# Definer prompts
ANALYSIS_PROMPT = """
Analyser denne LinkedIn-profilen grundig:

PROFIL:
{raw_profile}

MÅLROLLE:
{target_role}

TILGJENGELIG DATA:
{available_data}

FORVENTET OUTPUT FORMAT:
{schema}
"""

PRIORITY_PROMPT = """Evaluer og prioriter disse brukerne for {target_role}.
Max resultater: {max_results}

BRUKERE:
{users}

TILGJENGELIG DATA:
{available_data}

FORVENTET OUTPUT FORMAT:
{schema}
"""

# Bind modeller til strukturert output
analysis_chain = (
    ChatPromptTemplate.from_messages([
        ("system", analysis_prompt),
        ("human", ANALYSIS_PROMPT)
    ])
    | llm.with_structured_output(User, method="json_mode")
)

priority_chain = (
    ChatPromptTemplate.from_messages([
        ("system", priority_prompt),
        ("human", PRIORITY_PROMPT)
    ])
    | llm.with_structured_output(PriorityAnalysis, method="json_mode")
)

# SCREENING NODE
@traceable(run_type="chain", name="hunter_collection")
def collect_hunter_data(state: dict, config: RunnableConfig) -> dict:
    """Henter kontakter fra Hunter.io"""
    try:
        hunter_data = hunter_tool.invoke({
            "domain": state["config"]["domain"],
            "api_key": os.getenv("HUNTER_API_KEY")
        })
        
        validated_data = HunterResponse(**hunter_data)
        
        return {
            "messages": [
                ToolMessage(
                    tool_call_id="hunter_success",
                    tool_name="hunter",
                    content=f"Hentet {len(validated_data.emails)} kontakter"
                )
            ],
            "users": [{"email": email["value"], "first_name": email.get("first_name"), "last_name": email.get("last_name"), "role": email.get("position"), "linkedin_url": email.get("linkedin"), "confidence": str(email.get("confidence")) if email.get("confidence") else None, "sources": ["hunter"]} for email in validated_data.emails],
            "config": state["config"]
        }
    except Exception as e:
        return {
            "messages": [
                ToolMessage(
                    tool_call_id="hunter_error",
                    tool_name="hunter",
                    content=f"Feil: {str(e)}"
                )
            ],
            "users": [],
        }

# PRIORITERING NODE
@traceable(run_type="chain", name="prioritize_users")
def prioritize_users(state: dict, config: RunnableConfig) -> dict:
    """Prioriterer brukere basert på deres egnethet for målrollen."""
    # Hent alle brukere fra state
    all_users = state["users"]
    
    if not all_users:
        return {
            "messages": [HumanMessage(content="Ingen brukere å prioritere")],
            "users": [],
            "config": state["config"]
        }
    
    try:
        response = priority_chain.invoke({
            "target_role": state['config']['target_role'],
            "users": json.dumps(all_users, indent=2),
            "available_data": json.dumps({"domain": state['config']['domain']}, indent=2),
            "max_results": state['config'].get('max_results', 5),
            "schema": get_model_schema(PriorityAnalysis)
        })
        
        try:
            # Start med alle brukere
            updated_users = all_users.copy()
            
            # Oppdater de som ble prioritert
            for i, user in enumerate(updated_users):
                if user["email"] in {p.email for p in response.users}:
                    priority_user = next(p for p in response.users if p.email == user["email"])
                    # Valider score
                    if not 0 <= priority_user.score <= 1:
                        raise ValueError(f"Ugyldig score {priority_user.score} for {user['email']}")
                    updated_users[i] = {
                        **user,
                        "priority_score": priority_user.score,
                        "priority_reason": priority_user.reason,
                        "sources": user["sources"] + ["prioritized"]
                    }
            
            return {
                "messages": [
                    AIMessage(content=f"Prioriterte {len(response.users)} brukere")
                ],
                "users": updated_users,
                "config": state["config"]
            }
        except json.JSONDecodeError as je:
            raise ValueError("Kunne ikke parse prioriteringsrespons som JSON")
        except Exception as ve:
            raise ValueError("Validering av prioriteringsrespons feilet")
            
    except Exception as e:
        return {
            "messages": [HumanMessage(content=f"Feil i prioritering: {str(e)}")],
            "users": state["users"],
            "config": state["config"]
        }

# LINKEDIN DATA NODE
@traceable(run_type="chain", name="get_linkedin_data")
def get_linkedin_data(state: dict, config: RunnableConfig) -> dict:
    """Henter LinkedIn data for prioriterte brukere."""
    prioritized_users = [u for u in state["users"] 
                        if "prioritized" in u.get("sources", [])
                        and u.get("linkedin_url")]
    
    if not prioritized_users:
        return {
            "messages": [HumanMessage(content="Ingen brukere å berike")],
            "users": state["users"],
        }
    
    enriched = []
    messages = []
    
    for user in prioritized_users:
        try:
            linkedin_data = linkedin_tool.invoke({"linkedin_url": user["linkedin_url"]})
            enriched_user = {
                **user,
                "linkedin_raw_data": linkedin_data["data"],
                "sources": user["sources"] + ["linkedin"]
            }
            enriched.append(enriched_user)
            messages.append(
                ToolMessage(
                    tool_call_id=f"linkedin_{user['email']}",
                    tool_name="linkedin",
                    content=f"Hentet LinkedIn data for {user['email']}"
                )
            )
        except Exception as e:
            messages.append(
                ToolMessage(
                    tool_call_id=f"linkedin_error_{user['email']}",
                    tool_name="linkedin",
                    content=f"Feil: {str(e)}"
                )
            )
    
    return {
        "messages": messages,
        "users": enriched,
    }

# ANALYSE NODE
@traceable(run_type="chain", name="analyze_profiles")
def analyze_profiles(state: dict, config: RunnableConfig) -> dict:
    """Analyserer LinkedIn profiler."""
    users_to_analyze = [u for u in state["users"] 
                       if "linkedin" in u.get("sources", [])
                       and "linkedin_raw_data" in u]
    
    if not users_to_analyze:
        return {
            "messages": [SystemMessage(content="Ingen profiler å analysere")],
            "users": state["users"],
        }
    
    analyzed = []
    messages = []
    
    for user in users_to_analyze:
        try:
            response = analysis_chain.invoke({
                "raw_profile": json.dumps(user["linkedin_raw_data"], indent=2),
                "target_role": state["config"]["target_role"],
                "available_data": json.dumps({"domain": state['config']['domain']}, indent=2),
                "schema": get_model_schema(User)
            })
            
            try:
                analysis_results = response.dict()
                
                # Behold bare spesifikke felter fra original bruker
                analyzed_user = {
                    **analysis_results,  # Nye data først
                    "sources": user["sources"] + ["analyzed"]
                }
                # Fjern rådata etter analyse
                analyzed_user.pop("linkedin_raw_data", None)
                analyzed.append(analyzed_user)
                
                messages.append(
                    ToolMessage(
                        tool_call_id=f"analyze_{user['email']}",
                        tool_name="analyze",
                        content=f"Analyserte profil for {user['email']}"
                    )
                )
            except json.JSONDecodeError as je:
                raise ValueError(f"Kunne ikke parse JSON fra LLM respons for {user['email']}")
            except Exception as ve:
                raise ValueError(f"Validering feilet for {user['email']}")
                
        except Exception as e:
            messages.append(
                ToolMessage(
                    tool_call_id=f"analyze_error_{user['email']}",
                    tool_name="analyze",
                    content=f"Feil ved analyse av {user['email']}: {str(e)}"
                )
            )
    
    return {
        "messages": messages,
        "users": analyzed,
    }

@traceable(run_type="chain", name="create_crm_contacts")
def create_crm_contacts(state: dict, config: RunnableConfig) -> dict:
    """Oppretter kontakter i CRM-systemet og lagrer person_id i state."""
    # Filtrer ut kun analyserte brukere
    analyzed_users = [
        user for user in state["users"] 
        if user.get("sources") and "analyzed" in user.get("sources", [])
    ]
    
    if not analyzed_users:
        return state  # Ingen endringer hvis ingen brukere
    
    updated_users = state["users"].copy()
    
    for user in analyzed_users:
        try:
            # Opprett kontakt i Attio
            person_data = {
                "data": {
                    "values": {
                        "email_addresses": [user.get("email")],
                        "name": f"{user.get('first_name')} {user.get('last_name')}",
                        "job_title": user.get("role"),
                        "linkedin": user.get("linkedin_url")
                    }
                }
            }
            
            # Fjern tomme felter
            for key in list(person_data["data"]["values"].keys()):
                if not person_data["data"]["values"][key]:
                    del person_data["data"]["values"][key]
            
            # Opprett personen i Attio
            person_response = assert_person_in_attio(json.dumps(person_data))
            
            # Hent person_id fra responsen
            person_response_json = json.loads(person_response) if isinstance(person_response, str) else person_response
            person_id = person_response_json["data"]["id"]["record_id"]
            
            # Oppdater bruker med person_id og CRM-info
            user_with_id = {
                **user,
                "attio_person_id": person_id,
                "crm": {
                    "contact_created": True,
                    "contact_created_at": person_response_json["data"]["created_at"],
                    "note_created": False
                },
                "sources": user.get("sources", []) + ["crm"]
            }
            
            # Oppdater brukerlisten
            updated_users = merge_users(updated_users, [user_with_id])
            
        except Exception as e:
            print(f"Feil ved oppretting av kontakt for {user.get('email')}: {str(e)}")
            
            # Oppdater bruker med feilinformasjon
            user_with_error = {
                **user,
                "crm": {
                    "contact_created": False,
                    "contact_error": str(e)
                }
            }
            
            # Oppdater brukerlisten
            updated_users = merge_users(updated_users, [user_with_error])
    
    return {
        **state,
        "users": updated_users
    }

@traceable(run_type="chain", name="create_crm_notes")
def create_crm_notes(state: dict, config: RunnableConfig) -> dict:
    """Oppretter notater for brukere med person_id med fokus på salgsverdige detaljer."""
    # Filtrer ut brukere som har person_id
    users_with_person_id = [
        user for user in state["users"] 
        if user.get("attio_person_id")
    ]
    
    if not users_with_person_id:
        return state  # Ingen endringer hvis ingen brukere med person_id
    
    updated_users = state["users"].copy()
    
    for user in users_with_person_id:
        try:
            # Opprett notat i Attio
            note_title = f"Salgsnotat: {user.get('first_name')} {user.get('last_name')} - {user.get('role')}"
            
            # Bygg notat-innhold med fokus på salgsverdige detaljer
            note_content = f"# Nøkkelinformasjon\n"
            
            # Legg til om-tekst hvis tilgjengelig (dette er en oppsummering)
            if user.get("about"):
                note_content += f"{user.get('about')}\n\n"
            
            # Legg til karriere-informasjon
            if user.get("career"):
                career = user.get("career", {})
                note_content += f"# Karriere\n"
                
                if career.get("current_role") and career.get("current_company"):
                    note_content += f"Nåværende stilling: {career.get('current_role')} hos {career.get('current_company')}\n"
                
                if career.get("years_in_company"):
                    note_content += f"Ansiennitet: {career.get('years_in_company')} år i nåværende selskap\n"
                
                if career.get("total_experience_years"):
                    note_content += f"Total erfaring: {career.get('total_experience_years')} år\n"
                
                if career.get("responsibilities") and len(career.get("responsibilities", [])) > 0:
                    note_content += f"\nAnsvarsområder:\n"
                    for resp in career.get("responsibilities", []):
                        note_content += f"- {resp}\n"
                
                note_content += "\n"
            
            # Legg til ekspertise
            if user.get("expertise"):
                expertise = user.get("expertise", {})
                note_content += f"# Ekspertise og ferdigheter\n"
                
                if expertise.get("primary_skills") and len(expertise.get("primary_skills", [])) > 0:
                    note_content += f"Kjernekompetanse: {', '.join(expertise.get('primary_skills', []))}\n"
                
                if expertise.get("industry_knowledge") and len(expertise.get("industry_knowledge", [])) > 0:
                    note_content += f"Bransjekunnskap: {', '.join(expertise.get('industry_knowledge', []))}\n"
                
                if expertise.get("key_achievements") and len(expertise.get("key_achievements", [])) > 0:
                    note_content += f"\nViktige prestasjoner:\n"
                    for achievement in expertise.get("key_achievements", []):
                        note_content += f"- {achievement}\n"
                
                note_content += "\n"
            
            # Legg til personlighet og kommunikasjonsstil
            if user.get("personality"):
                personality = user.get("personality", {})
                note_content += f"# Personlighet og kommunikasjonsstil\n"
                
                if personality.get("communication", {}).get("primary_style"):
                    note_content += f"Kommunikasjonsstil: {personality.get('communication', {}).get('primary_style')}\n"
                
                if personality.get("work_style", {}).get("problem_solving"):
                    note_content += f"Problemløsning: {personality.get('work_style', {}).get('problem_solving')}\n"
                
                if personality.get("motivations", {}).get("career_drivers") and len(personality.get("motivations", {}).get("career_drivers", [])) > 0:
                    note_content += f"\nMotiveres av:\n"
                    for driver in personality.get("motivations", {}).get("career_drivers", []):
                        note_content += f"- {driver}\n"
                
                note_content += "\n"
            
            # Legg til prioriteringsinformasjon hvis tilgjengelig
            if user.get("priority_score") and user.get("priority_reason"):
                note_content += f"# Prioritering for {state['config']['target_role']}\n"
                note_content += f"Score: {user.get('priority_score')}\n"
                note_content += f"Begrunnelse: {user.get('priority_reason')}\n\n"
            
            # Legg til kontaktinformasjon og tips for oppfølging
            note_content += f"# Tips for oppfølging\n"
            
            if user.get("personality", {}).get("communication", {}).get("key_phrases") and len(user.get("personality", {}).get("communication", {}).get("key_phrases", [])) > 0:
                note_content += "Nøkkelfraser å referere til:\n"
                for phrase in user.get("personality", {}).get("communication", {}).get("key_phrases", []):
                    note_content += f"- \"{phrase}\"\n"
            
            note_data = {
                "data": {
                    "parent_object": "people",
                    "parent_record_id": user["attio_person_id"],
                    "title": note_title,
                    "format": "plaintext",
                    "content": note_content
                }
            }
            
            # Opprett notatet i Attio
            note_response = create_note_in_attio(json.dumps(note_data))
            note_response_json = json.loads(note_response) if isinstance(note_response, str) else note_response
            
            # Oppdater bruker med notat-info
            user_with_note = {
                **user,
                "crm": {
                    **(user.get("crm", {})),
                    "note_created": True,
                    "note_created_at": note_response_json["data"]["created_at"],
                    "note_id": note_response_json["data"]["id"]
                }
            }
            
            # Oppdater brukerlisten
            updated_users = merge_users(updated_users, [user_with_note])
            
        except Exception as e:
            print(f"Feil ved oppretting av notat for {user.get('email')}: {str(e)}")
            
            # Oppdater bruker med feilinformasjon
            user_with_error = {
                **user,
                "crm": {
                    **(user.get("crm", {})),
                    "note_created": False,
                    "note_error": str(e)
                }
            }
            
            # Oppdater brukerlisten
            updated_users = merge_users(updated_users, [user_with_error])
    
    return {
        **state,
        "users": updated_users
    }

def create_workflow() -> StateGraph:
    """Oppretter workflow."""
    workflow = StateGraph(State)
    
    # Legg til noder
    workflow.add_node("collect", collect_hunter_data)
    workflow.add_node("prioritize", prioritize_users)
    workflow.add_node("get_linkedin_data", get_linkedin_data)
    workflow.add_node("analyze", analyze_profiles)
    workflow.add_node("create_crm_contacts", create_crm_contacts)
    workflow.add_node("create_crm_notes", create_crm_notes)
    
    # Definer flyt med START og END
    workflow.add_edge(START, "collect")
    workflow.add_edge("collect", "prioritize")
    workflow.add_edge("prioritize", "get_linkedin_data")
    workflow.add_edge("get_linkedin_data", "analyze")
    workflow.add_edge("analyze", "create_crm_contacts")
    workflow.add_edge("create_crm_contacts", "create_crm_notes")
    workflow.add_edge("create_crm_notes", END)
    
    # Betinget routing - stopp hvis ingen brukere funnet
    workflow.add_conditional_edges(
        "collect",
        lambda s: "prioritize" if s["users"] else END
    )

    # Betinget routing - hopp over CRM hvis CRM_INTEGRATION er deaktivert
    workflow.add_conditional_edges(
        "analyze",
        lambda s: "create_crm_contacts" if os.getenv("ENABLE_CRM_INTEGRATION", "false").lower() == "true" else END
    )

    return workflow.compile()

def get_config() -> RunnableConfig:
    return RunnableConfig(
        callbacks=[],
        tags=["prospect-agent"],
        metadata={"version": "1.0"}
    )

# Compile workflow
app = create_workflow()

@traceable(name="analyze_domain", project=os.getenv("LANGCHAIN_PROJECT", "prospect-agent"))
def analyze_domain(domain: str, target_role: str = None, max_results: int = 5) -> Dict[str, Any]:
    """
    Analyser et domene og finn relevante personer basert på målrollen.
    
    Args:
        domain: Domenet som skal analyseres
        target_role: Målrollen som skal brukes for å finne relevante personer
        max_results: Maksimalt antall resultater som skal returneres
        
    Returns:
        Dict med analyserte brukere
    """
    # Kjør workflowen
    result = app.invoke({
        "messages": [],
        "users": [],
        "config": SearchConfig(
            domain=domain,
            target_role=target_role,
            max_results=max_results
        )
    }, config=get_config())
    
    # Konverter resultatet til et serialiserbart format
    serializable_result = {}
    if "users" in result:
        serializable_result["users"] = result["users"]
    
    # Evaluer resultatet hvis evaluering er aktivert
    # Importer her for å unngå sirkularitet
    from evaluate import evaluate_result
    evaluate_result(domain, target_role, serializable_result)
    
    return result

__all__ = ['app', 'get_config', 'analyze_domain']