from typing import Annotated, List, Dict, Union, TypedDict, Any
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph
from langchain_core.runnables import RunnableConfig
from langsmith import traceable
from langsmith.wrappers import wrap_openai
from openai import OpenAI
import json
import os
from dotenv import load_dotenv
from tools import linkedin_tool, hunter_tool
from prompts import (
    ANALYSIS_PROMPT, 
    PRIORITY_PROMPT,
    get_model_schema,
)
from models import (
    SearchConfig, 
    PriorityAnalysis,
    HunterResponse,
    User,
    State,
)
import logging
from langchain.prompts import ChatPromptTemplate
from system_prompts import ANALYSIS_SYSTEM_PROMPT, PRIORITY_SYSTEM_PROMPT

load_dotenv()

# Konfigurer logging
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')
for logger in ['langchain', 'langchain_core', 'langchain_openai', 'openai']:
    logging.getLogger(logger).setLevel(logging.ERROR)

# Configs
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0

# Wrap OpenAI client for better tracing
openai_client = wrap_openai(OpenAI())

# Opprett LLM instans
llm = ChatOpenAI(
    model_name=os.getenv("MODEL_NAME", DEFAULT_MODEL),
    temperature=float(os.getenv("TEMPERATURE", DEFAULT_TEMPERATURE))
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

def extract_json_from_response(content: str) -> str:
    """Ekstraherer JSON fra en LLM-respons som kan inneholde markdown."""
    if content.startswith("```"):
        # Finn slutten av første linje (språk-indikatoren)
        first_newline = content.find('\n')
        # Finn slutten av kodeblokken
        end_marker = content.rfind("```")
        # Ekstraher bare JSON-innholdet
        return content[first_newline:end_marker].strip()
    return content

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
        response = llm.invoke([
            SystemMessage(content=PRIORITY_SYSTEM_PROMPT),
            HumanMessage(content=PRIORITY_PROMPT.format(
                target_role=state['config']['target_role'],
                prospects=json.dumps(all_users, indent=2),
                available_data=json.dumps({"domain": state['config']['domain']}, indent=2),
                model_schema=get_model_schema(PriorityAnalysis),
                max_results=state['config'].get('max_results', 5)
            ))
        ])

        if not isinstance(response, AIMessage):
            raise ValueError(f"Uventet respons type: {type(response)}")
        
        # Logg responsen for debugging
        logging.info(f"LLM prioriteringsrespons: {response.content[:500]}...")
        
        try:
            content = extract_json_from_response(response.content)
            analysis = PriorityAnalysis(**json.loads(content))
            
            # Start med alle brukere
            updated_users = all_users.copy()
            
            # Oppdater de som ble prioritert
            for i, user in enumerate(updated_users):
                if user["email"] in {p.email for p in analysis.users}:
                    priority_user = next(p for p in analysis.users if p.email == user["email"])
                    updated_users[i] = {
                        **user,
                        "priority_score": priority_user.score,
                        "priority_reason": priority_user.reason,
                        "sources": user["sources"] + ["prioritized"]
                    }
            
            return {
                "messages": [
                    AIMessage(content=f"Prioriterte {len(analysis.users)} brukere")
                ],
                "users": updated_users,
                "config": state["config"]
            }
        except json.JSONDecodeError as je:
            error_msg = "Kunne ikke parse prioriteringsrespons som JSON"
            logging.error(f"{error_msg}: {str(je)}")
            logging.error(f"Rårespons: {response.content[:1000]}...")
            raise ValueError(error_msg)
        except Exception as ve:
            error_msg = "Validering av prioriteringsrespons feilet"
            logging.error(f"{error_msg}: {str(ve)}")
            raise ValueError(error_msg)
            
    except Exception as e:
        logging.error(f"Feil i prioritering: {str(e)}")
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
            "messages": [HumanMessage(content="Ingen profiler å analysere")],
            "users": state["users"],
        }
    
    analyzed = []
    messages = []
    
    for user in users_to_analyze:
        try:
            # Send rådata direkte til analyse - system message er nå utenfor state
            response = llm.invoke([
                SystemMessage(content=ANALYSIS_SYSTEM_PROMPT),
                HumanMessage(content=ANALYSIS_PROMPT.format(
                    raw_profile=json.dumps(user["linkedin_raw_data"], indent=2),
                    target_role=state["config"]["target_role"],
                    model_schema=get_model_schema(User)
                ))
            ])
            
            if not isinstance(response, AIMessage):
                raise ValueError(f"Uventet respons type: {type(response)}")
            
            # Logg responsen for debugging
            logging.info(f"LLM respons for {user['email']}: {response.content[:500]}...")
                
            try:
                content = extract_json_from_response(response.content)
                analysis_results = json.loads(content)
                logging.info(f"Vellykket JSON parsing for {user['email']}")
                
                # La modellen validere dataene og konverter til dict
                analysis_results = User(**analysis_results).dict()
                logging.info(f"Vellykket validering for {user['email']}")
                
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
                error_msg = f"Kunne ikke parse JSON fra LLM respons for {user['email']}: {str(je)}"
                logging.error(error_msg)
                logging.error(f"Rårespons: {response.content[:1000]}...")
                raise ValueError(error_msg)
            except Exception as ve:
                error_msg = f"Validering feilet for {user['email']}: {str(ve)}"
                logging.error(error_msg)
                raise ValueError(error_msg)
                
        except Exception as e:
            error_msg = f"Feil ved analyse av {user['email']}: {str(e)}"
            logging.error(error_msg)
            messages.append(
                ToolMessage(
                    tool_call_id=f"analyze_error_{user['email']}",
                    tool_name="analyze",
                    content=error_msg
                )
            )
    
    return {
        "messages": messages,
        "users": analyzed,
    }

# Oppdater workflow
def create_workflow() -> StateGraph:
    """Oppretter workflow."""
    workflow = StateGraph(State)
    
    # Legg til noder
    workflow.add_node("collect", collect_hunter_data)
    workflow.add_node("prioritize", prioritize_users)
    workflow.add_node("get_linkedin_data", get_linkedin_data)
    workflow.add_node("analyze", analyze_profiles)
    
    # Sett entry point
    workflow.set_entry_point("collect")
    
    # Definer flyt
    workflow.add_edge("collect", "prioritize")
    workflow.add_edge("prioritize", "get_linkedin_data")
    workflow.add_edge("get_linkedin_data", "analyze")
    workflow.add_edge("analyze", "__end__")
    
    # Betinget routing - stopp hvis ingen brukere funnet
    workflow.add_conditional_edges(
        "collect",
        lambda s: "prioritize" if s["users"] else "__end__"
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

def analyze_domain(
    domain: str,
    target_role: str,
    max_results: int = 5
) -> Dict[str, Any]:
    """Kjør full analyse av et domene."""
    return app.invoke({
        "messages": [],
        "users": [],
        "config": SearchConfig(
            domain=domain,
            target_role=target_role,
            max_results=max_results
        )
    })

__all__ = ['app', 'get_config', 'analyze_domain']