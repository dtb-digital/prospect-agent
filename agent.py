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
from tools import linkedin_tool, hunter_tool, create_note_in_attio, create_person_in_attio
from models import (
    SearchConfig, 
    PriorityAnalysis,
    HunterResponse,
    User,
    State,
    merge_users,
)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from prompt_hub import get_prompt_from_hub
import copy
from datetime import datetime

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

# Hent prompter direkte fra LangSmith
try:
    analysis_prompt = get_prompt_from_hub("prospect-agent-analysis-prompt")
    priority_prompt = get_prompt_from_hub("prospect-agent-priority-prompt")
except ValueError as e:
    print(f"KRITISK FEIL: {str(e)}")
    print("\nFor å løse dette problemet:")
    print("1. Sørg for at LANGCHAIN_API_KEY er satt i .env-filen")
    print("2. Sørg for at promptene eksisterer i LangSmith")
    print("3. Eller synkroniser prompter fra lokale filer med: python -m prompt_hub sync_files_to_prompts")
    raise

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

@traceable(name="create_crm_contacts")
def create_crm_contacts(state: State, config: RunnableConfig) -> State:
    """Oppretter kontakter i CRM-systemet."""
    # Sjekk om CRM-integrasjon er aktivert
    if os.getenv("ENABLE_CRM_INTEGRATION") != "true":
        print("CRM-integrasjon er deaktivert. Hopper over kontaktopprettelse.")
        return state
    
    # Kopier state for å unngå å endre originalen
    new_state = copy.deepcopy(state)
    
    # Gå gjennom alle brukere
    for i, user in enumerate(new_state["users"]):
        print(f"Oppretter kontakt for {user.get('email')}")
        
        # Opprett kontakt i Attio (send hele user-objektet)
        response = create_person_in_attio(user)
        
        # Sjekk om opprettelsen var vellykket
        if "error" not in response and "data" in response:
            # Legg til CRM-informasjon i brukeren
            if "crm" not in user:
                user["crm"] = {}
            
            user["crm"]["contact_created"] = True
            user["crm"]["contact_id"] = response["data"]["id"]
            print(f"Kontakt opprettet for {user.get('email')} med ID {response['data']['id']}")
        else:
            # Legg til feilmelding i brukeren
            if "crm" not in user:
                user["crm"] = {}
            
            user["crm"]["contact_created"] = False
            user["crm"]["contact_error"] = response.get("error", "Ukjent feil")
            print(f"Feil ved opprettelse av kontakt for {user.get('email')}: {response.get('error', 'Ukjent feil')}")
    
    return new_state

@traceable(run_type="chain", name="crm_notes")
def create_crm_notes(state: dict, config: RunnableConfig) -> dict:
    """Oppretter notater i CRM-systemet basert på analyserte brukere."""
    if not os.getenv("ENABLE_CRM_INTEGRATION", "false").lower() == "true":
        return state
    
    print("Oppretter notater i CRM-systemet...")
    
    try:
        # Lag en kopi av brukerne for å unngå å endre originalen direkte
        updated_users = copy.deepcopy(state.get("users", []))
        
        for i, user in enumerate(updated_users):
            if user.get("crm", {}).get("contact_created") and not user.get("crm", {}).get("note_created"):
                person_id = user.get("attio_person_id") or user.get("crm", {}).get("contact_id")
                if not person_id:
                    print(f"Ingen person-ID funnet for {user.get('email')}")
                    continue
                
                # Lag notat-innhold basert på brukerdata
                note_content = f"# Analyse av {user.get('first_name', '')} {user.get('last_name', '')}\n\n"
                
                if user.get("about"):
                    note_content += f"## Om personen\n{user.get('about')}\n\n"
                
                if user.get("career"):
                    note_content += "## Karriere\n"
                    career = user.get("career", {})
                    if career.get("current_role"):
                        note_content += f"- Nåværende rolle: {career.get('current_role')}\n"
                    if career.get("current_company"):
                        note_content += f"- Nåværende selskap: {career.get('current_company')}\n"
                    if career.get("responsibilities"):
                        note_content += "- Ansvarsområder:\n"
                        for resp in career.get("responsibilities", []):
                            note_content += f"  - {resp}\n"
                    note_content += "\n"
                
                if user.get("expertise"):
                    note_content += "## Ekspertise\n"
                    expertise = user.get("expertise", {})
                    if expertise.get("primary_skills"):
                        note_content += "- Primære ferdigheter:\n"
                        for skill in expertise.get("primary_skills", []):
                            note_content += f"  - {skill}\n"
                    if expertise.get("key_achievements"):
                        note_content += "- Nøkkelprestasjoner:\n"
                        for achievement in expertise.get("key_achievements", []):
                            note_content += f"  - {achievement}\n"
                    note_content += "\n"
                
                if user.get("personality"):
                    note_content += "## Personlighet\n"
                    personality = user.get("personality", {})
                    if personality.get("communication", {}).get("primary_style"):
                        note_content += f"- Kommunikasjonsstil: {personality.get('communication', {}).get('primary_style')}\n"
                    if personality.get("motivations", {}).get("career_drivers"):
                        note_content += "- Karrieredrivere:\n"
                        for driver in personality.get("motivations", {}).get("career_drivers", []):
                            note_content += f"  - {driver}\n"
                    note_content += "\n"
                
                # Legg til kilde og dato
                note_content += f"\nKilde: Prospect Agent\nDato: {datetime.now().strftime('%Y-%m-%d')}"
                
                print(f"Oppretter notat for {user.get('email')} med person-ID {person_id}")
                
                try:
                    # Opprett notat i Attio med den nye funksjonen
                    response = create_note_in_attio({
                        "person_id": person_id,
                        "content": note_content,
                        "title": f"Analyse av {user.get('first_name', '')} {user.get('last_name', '')}"
                    })
                    
                    print(f"Attio API-respons: {json.dumps(response, indent=2)}")
                    
                    # Sjekk om opprettelsen var vellykket
                    if "error" not in response and "data" in response:
                        # Oppdater brukeren med CRM-informasjon
                        if "crm" not in updated_users[i]:
                            updated_users[i]["crm"] = {}
                        
                        updated_users[i]["crm"]["note_created"] = True
                        updated_users[i]["crm"]["note_created_at"] = response.get("data", {}).get("created_at")
                        updated_users[i]["crm"]["note_id"] = response.get("data", {}).get("id")
                        print(f"Notat opprettet for {user.get('email')} med ID {response.get('data', {}).get('id')}")
                    else:
                        # Legg til feilmelding i brukeren
                        if "crm" not in updated_users[i]:
                            updated_users[i]["crm"] = {}
                        
                        updated_users[i]["crm"]["note_created"] = False
                        updated_users[i]["crm"]["note_error"] = response.get("error", "Ukjent feil")
                        print(f"Feil ved opprettelse av notat for {user.get('email')}: {response.get('error', 'Ukjent feil')}")
                except Exception as e:
                    print(f"Feil ved opprettelse av notat: {str(e)}")
        
        # Returner oppdatert state
        return {
            **state,
            "users": updated_users
        }
    except Exception as e:
        print(f"Feil ved opprettelse av notater: {str(e)}")
        return state

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