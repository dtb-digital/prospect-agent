import os
import json
from dotenv import load_dotenv
from agent import analyze_domain
import sys

# Last inn miljøvariabler
load_dotenv()

# Aktiver CRM-integrasjon for testen
os.environ["ENABLE_CRM_INTEGRATION"] = "true"

def test_crm_integration():
    """Test av CRM-integrasjon med Attio."""
    
    # Last inn testdata
    with open("tests/test_data.json", "r") as f:
        test_data = json.load(f)
    
    # Kjør analysen
    domain = test_data.get("domain", "firi.com")
    target_role = test_data.get("target_role", "ceo eller produktleder")
    
    # Kjør analysen
    result = analyze_domain(domain, target_role, max_results=2)
    
    # Skriv ut brukerdata som sendes til agenten
    print("Brukerdata som sendes til agenten:")
    print(json.dumps({"users": result.get("users", []), "config": result.get("config", {})}, indent=2))
    
    # Skriv ut resultatet
    if "crm_results" in result:
        print("CRM-integrasjon resultat:")
        print(json.dumps({"content": str(result.get("crm_results"))}, indent=2))
    
    if "note_results" in result:
        print("CRM-notat resultat:")
        print(json.dumps({"content": str(result.get("note_results"))}, indent=2))
    
    # Sjekk at vi har fått et resultat
    assert result is not None
    assert "users" in result
    assert len(result["users"]) > 0
    
    # Sjekk at CRM-integrasjonen har kjørt
    if "crm_results" in result:
        assert len(result["crm_results"]) > 0
    
    # Sjekk at notat-opprettelsen har kjørt
    if "note_results" in result:
        assert len(result["note_results"]) > 0

if __name__ == "__main__":
    test_crm_integration() 