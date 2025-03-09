import os
import json
from dotenv import load_dotenv
import sys

# Legg til prosjektets rotmappe i Python-søkestien
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent import create_crm_contacts, create_crm_notes

# Last inn miljøvariabler
load_dotenv()

# Aktiver CRM-integrasjon for testen
os.environ["ENABLE_CRM_INTEGRATION"] = "true"

def test_crm_integration():
    """Test av CRM-integrasjon med Attio."""
    
    # Last inn testdata
    with open("tests/test_data.json", "r") as f:
        test_data = json.load(f)
    
    # Hent domene og målrolle fra testdata
    domain = test_data.get("domain", "firi.com")
    target_role = test_data.get("target_role", "ceo eller produktleder")
    
    # Bruk testbrukere fra test_data.json hvis tilgjengelig, ellers bruk standard testbruker
    test_users = test_data.get("users", [])
    
    if not test_users:
        # Bruk standard testbruker hvis ingen brukere er definert i test_data.json
        test_users = [{
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "role": "CEO",
            "linkedin_url": "https://www.linkedin.com/in/testuser/",
            "sources": ["hunter", "prioritized", "linkedin", "analyzed"],
            "about": "Dette er en testbruker for CRM-integrasjon.",
            "career": {
                "current_role": "CEO",
                "current_company": "Test Company",
                "years_in_company": 5
            },
            "expertise": {
                "primary_skills": ["Ledelse", "Strategi"]
            }
        }]
    
    # Simuler state
    state = {
        "users": test_users,
        "config": {
            "domain": domain,
            "target_role": target_role
        }
    }
    
    print("Testdata som brukes:")
    print(json.dumps(state, indent=2))
    
    # Kjør CRM-kontakt-opprettelse
    contact_result = create_crm_contacts(state, {})
    
    # Kjør CRM-notat-opprettelse
    final_result = create_crm_notes(contact_result, {})
    
    # Skriv ut resultatet
    print("Brukerdata etter CRM-integrasjon:")
    print(json.dumps({"users": final_result["users"]}, indent=2))
    
    # Sjekk at vi har fått et resultat
    assert final_result is not None
    assert "users" in final_result
    assert len(final_result["users"]) > 0
    
    # Sjekk at CRM-integrasjonen har kjørt
    users_with_crm = [user for user in final_result["users"] if user.get("crm")]
    assert len(users_with_crm) > 0
    
    # Sjekk at kontakter er opprettet
    contacts_created = [user for user in users_with_crm if user.get("crm", {}).get("contact_created")]
    assert len(contacts_created) > 0
    
    # Sjekk at notater er opprettet
    notes_created = [user for user in users_with_crm if user.get("crm", {}).get("note_created")]
    assert len(notes_created) > 0
    
    print(f"Test fullført: {len(contacts_created)} kontakter og {len(notes_created)} notater opprettet")

if __name__ == "__main__":
    test_crm_integration() 