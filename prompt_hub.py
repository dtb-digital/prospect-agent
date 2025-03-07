from langsmith import Client
from dotenv import load_dotenv
import os
import sys
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate

load_dotenv()

# Initialiser LangSmith klienten
client = Client()

# Hent prompter fra Prompt Hub
def get_prompt_from_hub(prompt_name, fallback_content=None):
    """
    Henter en prompt fra LangSmith Prompt Hub.
    
    Args:
        prompt_name: Navnet på prompten i LangSmith
        fallback_content: Innhold som skal brukes hvis prompten ikke finnes
        
    Returns:
        Innholdet i prompten
    """
    try:
        # Prøv å hente prompten direkte med pull_prompt
        try:
            prompt = client.pull_prompt(prompt_name)
            print(f"Hentet prompt '{prompt_name}' fra LangSmith")
            
            # Hent innholdet fra prompten
            if isinstance(prompt, ChatPromptTemplate) and hasattr(prompt, 'messages'):
                # ChatPromptTemplate har en liste med meldinger
                for message in prompt.messages:
                    if isinstance(message, SystemMessagePromptTemplate) and hasattr(message, 'prompt'):
                        # SystemMessagePromptTemplate har en prompt av typen PromptTemplate
                        if hasattr(message.prompt, 'template'):
                            return message.prompt.template
                
                # Hvis ingen systemmelding, returner template fra første melding
                if prompt.messages and hasattr(prompt.messages[0], 'prompt'):
                    if hasattr(prompt.messages[0].prompt, 'template'):
                        return prompt.messages[0].prompt.template
            
            # For StringPromptTemplate
            if hasattr(prompt, 'template'):
                return prompt.template
                
            return str(prompt)
            
        except Exception as e:
            print(f"Kunne ikke hente prompt med pull_prompt: {e}")
            
            # Prøv å finne prompten i listen over prompter
            prompts_response = client.list_prompts()
            prompts = prompts_response.repos if hasattr(prompts_response, 'repos') else []
            
            for prompt in prompts:
                if prompt.repo_handle == prompt_name:
                    print(f"Fant prompt '{prompt_name}' i listen, men kunne ikke hente innholdet")
                    print(f"Du kan se prompten i LangSmith UI: https://smith.langchain.com/hub/{prompt.repo_handle}")
                    
                    return fallback_content
            
            # Hvis vi kommer hit, fant vi ikke prompten
            print(f"Prompt '{prompt_name}' ikke funnet i LangSmith")
            
            # Opprett ny prompt hvis vi har fallback-innhold
            if fallback_content:
                print(f"Oppretter ny prompt '{prompt_name}' i LangSmith")
                # Konverter tekst til ChatPromptTemplate
                prompt_template = ChatPromptTemplate.from_messages([
                    ("system", fallback_content)
                ])
                # Bruk push_prompt med object-parameter
                client.push_prompt(prompt_name, object=prompt_template)
                return fallback_content
                
            return fallback_content
    except Exception as e:
        print(f"Feil ved henting av prompt '{prompt_name}': {e}")
        return fallback_content

# Oppdater en eksisterende prompt
def update_prompt_in_hub(prompt_name, content):
    """
    Oppdaterer en prompt i LangSmith Prompt Hub.
    
    Args:
        prompt_name: Navnet på prompten i LangSmith
        content: Innholdet som skal oppdateres
        
    Returns:
        True hvis oppdateringen var vellykket, False ellers
    """
    try:
        # Sjekk om prompten allerede eksisterer
        try:
            existing_prompt = client.pull_prompt(prompt_name)
            print(f"Prompt '{prompt_name}' finnes allerede i LangSmith")
            exists = True
        except Exception:
            exists = False
        
        # Opprett ChatPromptTemplate
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", content)
        ])
        
        # Bruk push_prompt med riktige parametere
        if exists:
            client.push_prompt(prompt_name, object=prompt_template)
            print(f"Oppdatert prompt '{prompt_name}' i LangSmith")
        else:
            client.push_prompt(prompt_name, object=prompt_template)
            print(f"Opprettet ny prompt '{prompt_name}' i LangSmith")
        
        return True
    except Exception as e:
        print(f"Kunne ikke oppdatere prompt '{prompt_name}': {e}")
        return False

# Legg til denne funksjonen for å debugge API-responsen
def debug_api_response(response, name="API-respons"):
    """Skriver ut detaljert informasjon om en API-respons."""
    print(f"\n--- DEBUG: {name} ---")
    print(f"Type: {type(response)}")
    print(f"Dir: {dir(response)}")
    
    if hasattr(response, "__dict__"):
        print(f"Dict: {response.__dict__}")
    
    try:
        import json
        print(f"JSON: {json.dumps(response, default=str)}")
    except:
        pass
    
    print("--- END DEBUG ---\n")
    return response

# Legg til disse funksjonene i prompt_hub.py

def sync_system_prompts():
    """Synkroniserer alle system-prompter til LangSmith."""
    from system_prompts import ANALYSIS_SYSTEM_PROMPT, PRIORITY_SYSTEM_PROMPT
    
    # Opprett eller oppdater promptene i LangSmith
    update_prompt_in_hub("prospect-agent-analysis-prompt", ANALYSIS_SYSTEM_PROMPT)
    update_prompt_in_hub("prospect-agent-priority-prompt", PRIORITY_SYSTEM_PROMPT)
    
    print("Alle system-prompter er synkronisert til LangSmith.")

def sync_from_langsmith():
    """Synkroniserer prompter fra LangSmith til lokale filer."""
    import os
    os.makedirs("prompts", exist_ok=True)
    
    # Hent prompter fra LangSmith
    analysis_prompt = get_prompt_from_hub("prospect-agent-analysis-prompt")
    priority_prompt = get_prompt_from_hub("prospect-agent-priority-prompt")
    
    # Lagre til lokale filer hvis vi fikk innholdet
    if analysis_prompt:
        with open("prompts/analysis_prompt.txt", "w") as f:
            f.write(analysis_prompt)
        print(f"Lagret analysis_prompt til prompts/analysis_prompt.txt")
    else:
        print("Kunne ikke hente analysis_prompt fra LangSmith")
    
    if priority_prompt:
        with open("prompts/priority_prompt.txt", "w") as f:
            f.write(priority_prompt)
        print(f"Lagret priority_prompt til prompts/priority_prompt.txt")
    else:
        print("Kunne ikke hente priority_prompt fra LangSmith")
    
    print("Prompter synkronisert fra LangSmith til lokale filer.")

def sync_prompts():
    """Synkroniserer prompter med LangSmith."""
    prompts = {
        "prospect-agent-analysis-prompt": "prompts/analysis_prompt.txt",
        "prospect-agent-priority-prompt": "prompts/priority_prompt.txt",
        "prospect-agent-analysis-prompt-v2": "prompts/analysis_prompt_v2.txt",
        "prospect-agent-priority-prompt-v2": "prompts/priority_prompt_v2.txt",
        "prospect-agent-attio-prompt": "prompts/attio_prompt.txt"
    }
    
    for prompt_name, file_path in prompts.items():
        try:
            with open(file_path, "r") as f:
                content = f.read()
            
            # Sjekk om prompten finnes
            try:
                existing_prompt = client.pull_prompt(prompt_name)
                print(f"Prompt '{prompt_name}' finnes allerede, oppdaterer...")
            except:
                print(f"Prompt '{prompt_name}' finnes ikke, oppretter...")
            
            # Opprett eller oppdater prompten
            # Konverter tekst til ChatPromptTemplate
            prompt_template = ChatPromptTemplate.from_messages([
                ("system", content)
            ])
            # Bruk push_prompt med riktige parametere
            client.push_prompt(prompt_name, object=prompt_template)
            print(f"Synkronisert prompt '{prompt_name}' med LangSmith")
        except Exception as e:
            print(f"Feil ved synkronisering av prompt '{prompt_name}': {e}")

def delete_prompt(prompt_name):
    """Sletter en prompt fra LangSmith."""
    try:
        # Sjekk om prompten eksisterer
        try:
            existing_prompt = client.pull_prompt(prompt_name)
            print(f"Prompt '{prompt_name}' finnes i LangSmith, sletter...")
            
            # Slett prompten
            client.delete_prompt(prompt_name)
            print(f"Slettet prompt '{prompt_name}' fra LangSmith")
            return True
        except Exception as e:
            print(f"Prompt '{prompt_name}' finnes ikke i LangSmith: {e}")
            return False
    except Exception as e:
        print(f"Feil ved sletting av prompt '{prompt_name}': {e}")
        return False

def cleanup_prompts():
    """Rydder opp i prompter i LangSmith."""
    # Liste over prompter vi vil beholde
    keep_prompts = [
        "prospect-agent-analysis-prompt",
        "prospect-agent-priority-prompt",
        "prospect-agent-analysis-prompt-v2",
        "prospect-agent-priority-prompt-v2",
        "prospect-agent-attio-prompt"
    ]
    
    try:
        # Hent alle prompter
        prompts_response = client.list_prompts()
        
        if hasattr(prompts_response, 'repos'):
            prompts = prompts_response.repos
            print(f"Fant {len(prompts)} prompter i LangSmith")
            
            # Gå gjennom alle prompter
            for prompt in prompts:
                if prompt.repo_handle not in keep_prompts:
                    print(f"Sletter prompt '{prompt.repo_handle}'...")
                    delete_prompt(prompt.repo_handle)
                else:
                    print(f"Beholder prompt '{prompt.repo_handle}'")
            
            print("Opprydding fullført")
        else:
            print("Kunne ikke finne prompter i responsen")
    except Exception as e:
        print(f"Feil ved opprydding av prompter: {e}")

def cleanup_local_prompts():
    """Rydder opp i lokale promptfiler."""
    # Liste over promptfiler vi vil beholde
    keep_files = [
        "prompts/analysis_prompt.txt",
        "prompts/priority_prompt.txt",
        "prompts/analysis_prompt_v2.txt",
        "prompts/priority_prompt_v2.txt",
        "prompts/attio_prompt.txt"
    ]
    
    try:
        # Sjekk om prompts-mappen finnes
        if not os.path.exists("prompts"):
            print("Prompts-mappen finnes ikke")
            return
        
        # Gå gjennom alle filer i prompts-mappen
        for file in os.listdir("prompts"):
            file_path = os.path.join("prompts", file)
            
            # Sjekk om filen er en tekstfil
            if file.endswith(".txt") and os.path.isfile(file_path):
                if file_path not in keep_files:
                    print(f"Sletter fil '{file_path}'...")
                    os.remove(file_path)
                else:
                    print(f"Beholder fil '{file_path}'")
        
        print("Opprydding av lokale promptfiler fullført")
    except Exception as e:
        print(f"Feil ved opprydding av lokale promptfiler: {e}")

# Oppdater kommandolinje-grensesnittet
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Bruk: python prompt_hub.py <kommando> [argumenter]")
        print("Kommandoer:")
        print("  list - List alle prompter")
        print("  get <prompt_name> - Hent en prompt")
        print("  update <prompt_name> <fil> - Oppdater en prompt fra fil")
        print("  create <prompt_name> <fil> - Opprett en ny prompt fra fil")
        print("  delete <prompt_name> - Slett en prompt")
        print("  sync-to-langsmith - Synkroniser system-prompter til LangSmith")
        print("  sync-from-langsmith - Synkroniser prompter fra LangSmith til lokale filer")
        print("  sync-prompts - Synkroniser prompter med LangSmith")
        print("  cleanup - Rydd opp i prompter")
        print("  cleanup-local - Rydd opp i lokale promptfiler")
        print("  cleanup-all - Rydd opp i prompter og lokale promptfiler")
        sys.exit(1)
        
    command = sys.argv[1]
    
    if command == "list":
        try:
            print("Henter prompter fra LangSmith...")
            prompts_response = client.list_prompts()
            
            # Hent promptene fra repos-attributtet
            if hasattr(prompts_response, 'repos'):
                prompts = prompts_response.repos
                print(f"Fant {len(prompts)} prompter:")
                for prompt in prompts:
                    print(f"  {prompt.repo_handle} (ID: {prompt.id})")
            else:
                print("Kunne ikke finne prompter i responsen.")
                debug_api_response(prompts_response, "list_prompts response")
        except Exception as e:
            print(f"Feil ved listing av prompter: {e}")
            
    elif command == "get" and len(sys.argv) >= 3:
        prompt_name = sys.argv[2]
        content = get_prompt_from_hub(prompt_name)
        if content:
            print(f"Innhold i prompt '{prompt_name}':")
            print(content)
        else:
            print(f"Prompt '{prompt_name}' ikke funnet")
            
    elif command == "update" and len(sys.argv) >= 4:
        prompt_name = sys.argv[2]
        file_path = sys.argv[3]
        
        try:
            with open(file_path, "r") as f:
                content = f.read()
                
            success = update_prompt_in_hub(prompt_name, content)
            if success:
                print(f"Prompt '{prompt_name}' oppdatert fra fil '{file_path}'")
            else:
                print(f"Kunne ikke oppdatere prompt '{prompt_name}'")
        except Exception as e:
            print(f"Feil ved lesing av fil '{file_path}': {e}")
            
    elif command == "create" and len(sys.argv) >= 4:
        prompt_name = sys.argv[2]
        file_path = sys.argv[3]
        
        try:
            with open(file_path, "r") as f:
                content = f.read()
                
            # Konverter tekst til ChatPromptTemplate
            prompt_template = ChatPromptTemplate.from_messages([
                ("system", content)
            ])
            # Bruk push_prompt med object-parameter
            client.push_prompt(prompt_name, object=prompt_template)
            print(f"Opprettet prompt '{prompt_name}'")
        except Exception as e:
            print(f"Feil ved opprettelse av prompt '{prompt_name}': {e}")
            
    elif command == "delete" and len(sys.argv) >= 3:
        prompt_name = sys.argv[2]
        delete_prompt(prompt_name)
        
    elif command == "sync-to-langsmith":
        sync_system_prompts()
        
    elif command == "sync-from-langsmith":
        sync_from_langsmith()
        
    elif command == "sync-prompts":
        sync_prompts()
        
    elif command == "cleanup":
        cleanup_prompts()
        
    elif command == "cleanup-local":
        cleanup_local_prompts()
        
    elif command == "cleanup-all":
        cleanup_prompts()
        cleanup_local_prompts()
        
    else:
        print("Ukjent kommando eller manglende argumenter")
        sys.exit(1) 