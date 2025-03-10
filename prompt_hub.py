"""
Modul for å hente og synkronisere prompter med LangSmith Prompt Hub.
"""

from langsmith import Client
from dotenv import load_dotenv
import os
import json
from pathlib import Path
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

# Initialiser LangSmith klienten
client = Client()

def get_prompt_from_hub(prompt_name: str) -> str:
    """
    Henter en prompt fra LangSmith Prompt Hub.
    
    Args:
        prompt_name: Navnet på prompten i LangSmith
        
    Returns:
        Prompten som en streng
        
    Raises:
        ValueError: Hvis prompten ikke kan hentes
    """
    try:
        # Sjekk om LANGCHAIN_API_KEY er satt
        if not os.getenv("LANGCHAIN_API_KEY"):
            raise ValueError(f"LANGCHAIN_API_KEY er ikke satt. Kan ikke hente prompt '{prompt_name}'.")
        
        # Hent prompten fra LangSmith
        prompt = client.pull_prompt(prompt_name)
        
        # Hvis prompten inneholder en template, returner den
        if hasattr(prompt, "template"):
            return prompt.template
        
        # Ellers, returner prompten som en streng
        return str(prompt)
    
    except Exception as e:
        raise ValueError(f"Kunne ikke hente prompt '{prompt_name}' fra LangSmith: {str(e)}")

def push_prompt_to_hub(prompt_name: str, content: str) -> bool:
    """
    Oppdaterer eller oppretter en prompt i LangSmith Prompt Hub.
    
    Args:
        prompt_name: Navnet på prompten i LangSmith
        content: Innholdet som skal oppdateres
        
    Returns:
        True hvis oppdateringen var vellykket
        
    Raises:
        ValueError: Hvis prompten ikke kan oppdateres
    """
    try:
        # Sjekk om LANGCHAIN_API_KEY er satt
        if not os.getenv("LANGCHAIN_API_KEY"):
            raise ValueError(f"LANGCHAIN_API_KEY er ikke satt. Kan ikke oppdatere prompt '{prompt_name}'.")
        
        # Opprett ChatPromptTemplate
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", content)
        ])
        
        # Push prompten til LangSmith
        client.push_prompt(prompt_name, object=prompt_template)
        print(f"Oppdatert prompt '{prompt_name}' i LangSmith")
        
        return True
    except Exception as e:
        raise ValueError(f"Kunne ikke oppdatere prompt '{prompt_name}' i LangSmith: {str(e)}")

def sync_prompts_to_files() -> None:
    """
    Synkroniserer prompter fra LangSmith til lokale filer.
    
    Raises:
        ValueError: Hvis promptene ikke kan synkroniseres
    """
    try:
        # Sjekk om LANGCHAIN_API_KEY er satt
        if not os.getenv("LANGCHAIN_API_KEY"):
            raise ValueError("LANGCHAIN_API_KEY er ikke satt. Kan ikke synkronisere prompter.")
        
        # Opprett prompts-mappen hvis den ikke finnes
        prompts_dir = Path("prompts")
        prompts_dir.mkdir(exist_ok=True)
        
        # Hent alle prompter fra LangSmith
        prompts = client.list_prompts()
        
        for prompt in prompts:
            # Hent promptens innhold
            prompt_content = get_prompt_from_hub(prompt.name)
            
            # Lagre prompten til fil
            prompt_file = prompts_dir / f"{prompt.name}.txt"
            with open(prompt_file, "w") as f:
                f.write(prompt_content)
            
            print(f"Synkronisert prompt '{prompt.name}' til {prompt_file}")
    
    except Exception as e:
        raise ValueError(f"Kunne ikke synkronisere prompter: {str(e)}")

def sync_files_to_prompts() -> None:
    """
    Synkroniserer lokale filer til LangSmith prompter.
    
    Raises:
        ValueError: Hvis filene ikke kan synkroniseres
    """
    try:
        # Sjekk om LANGCHAIN_API_KEY er satt
        if not os.getenv("LANGCHAIN_API_KEY"):
            raise ValueError("LANGCHAIN_API_KEY er ikke satt. Kan ikke synkronisere filer.")
        
        # Sjekk om prompts-mappen finnes
        prompts_dir = Path("prompts")
        if not prompts_dir.exists():
            raise ValueError("Prompts-mappen finnes ikke.")
        
        # Gå gjennom alle filer i prompts-mappen
        for prompt_file in prompts_dir.glob("*.txt"):
            # Les promptens innhold
            with open(prompt_file, "r") as f:
                prompt_content = f.read()
            
            # Hent promptens navn fra filnavnet
            prompt_name = prompt_file.stem
            
            # Push prompten til LangSmith
            push_prompt_to_hub(prompt_name, prompt_content)
            
            print(f"Synkronisert fil {prompt_file} til prompt '{prompt_name}'")
    
    except Exception as e:
        raise ValueError(f"Kunne ikke synkronisere filer: {str(e)}")

# Legg til kommandolinje-grensesnitt
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Bruk: python -m prompt_hub <kommando>")
        print("Kommandoer:")
        print("  sync_prompts_to_files - Synkroniserer prompter fra LangSmith til lokale filer")
        print("  sync_files_to_prompts - Synkroniserer lokale filer til LangSmith prompter")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "sync_prompts_to_files":
        sync_prompts_to_files()
    elif command == "sync_files_to_prompts":
        sync_files_to_prompts()
    else:
        print(f"Ukjent kommando: {command}")
        print("Kommandoer:")
        print("  sync_prompts_to_files - Synkroniserer prompter fra LangSmith til lokale filer")
        print("  sync_files_to_prompts - Synkroniserer lokale filer til LangSmith prompter")
        sys.exit(1) 