import os
import json
from dotenv import load_dotenv
import sys

# Legg til prosjektets rotmappe i Python-søkestien
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent import create_crm_contacts, create_crm_notes
from tools import create_person_in_attio

# Last inn miljøvariabler
load_dotenv()

# Aktiver CRM-integrasjon for testen
os.environ["ENABLE_CRM_INTEGRATION"] = "true"

def test_crm_integration():
    """Test av CRM-integrasjon med Attio."""
    
    # Sjekk miljøvariabler
    print("\n--- Miljøvariabler ---")
    print(f"ENABLE_CRM_INTEGRATION: {os.getenv('ENABLE_CRM_INTEGRATION', 'ikke satt')}")
    print(f"ATTIO_API_KEY: {'Satt' if os.getenv('ATTIO_API_KEY') else 'Ikke satt'}")
    
    # Last inn testdata
    with open("tests/test_data.json", "r") as f:
        test_data = json.load(f)
    
    # Hent domene og målrolle fra testdata
    domain = test_data.get("domain", "firi.com")
    target_role = test_data.get("target_role", "ceo eller produktleder")
    
    # Bruk testbrukere fra test_data.json hvis tilgjengelig, ellers bruk standard testbruker
    test_users = test_data.get("users", [])
    
    # Manuell test av create_person_in_attio
    print("\n--- Manuell test av create_person_in_attio ---")
    test_user = test_users[0] if test_users else {
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "role": "CEO",
        "linkedin_url": "https://www.linkedin.com/in/testuser/"
    }
    
    try:
        response = create_person_in_attio({
            "email": test_user.get("email"),
            "first_name": test_user.get("first_name"),
            "last_name": test_user.get("last_name", ""),
            "title": test_user.get("role") or test_user.get("career", {}).get("current_role", ""),
            "linkedin_url": test_user.get("linkedin_url", "")
        })
        
        print(f"Respons fra create_person_in_attio: {json.dumps(response, indent=2)}")
        
        # Sjekk om opprettelsen var vellykket
        if "error" not in response and "data" in response:
            print(f"Person opprettet med ID: {response['data']['id']}")
        else:
            print(f"Feil ved opprettelse av person: {response.get('error', 'Ukjent feil')}")
    except Exception as e:
        print(f"Feil ved testing av create_person_in_attio: {e}")
    
    # Sjekk at testbrukerne inneholder nødvendig informasjon
    print("\n--- Testbrukere ---")
    for i, user in enumerate(test_users):
        print(f"Bruker {i+1}:")
        print(f"  Email: {user.get('email', 'Mangler')}")
        print(f"  First name: {user.get('first_name', 'Mangler')}")
        print(f"  Last name: {user.get('last_name', 'Mangler')}")
        print(f"  Role: {user.get('role', 'Mangler')}")
        print(f"  LinkedIn URL: {user.get('linkedin_url', 'Mangler')}")
    
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
    
    # Kjør CRM-kontakt-opprettelse (faktisk integrasjon)
    print("\n--- Oppretter kontakter i CRM ---")
    contact_result = create_crm_contacts(state, {})
    
    # Skriv ut resultatet etter kontaktopprettelse
    print("\nResultat etter kontaktopprettelse:")
    for user in contact_result["users"]:
        print(f"- {user.get('email')}: Kontakt opprettet: {user.get('crm', {}).get('contact_created', False)}")
    
    # Kjør CRM-notat-opprettelse (faktisk integrasjon)
    print("\n--- Oppretter notater i CRM ---")
    final_result = create_crm_notes(contact_result, {})
    
    # Skriv ut resultatet etter notatopprettelse
    print("\nResultat etter notatopprettelse:")
    for user in final_result["users"]:
        print(f"- {user.get('email')}: Kontakt opprettet: {user.get('crm', {}).get('contact_created', False)}, Notat opprettet: {user.get('crm', {}).get('note_created', False)}")
    
    # Skriv ut detaljert resultat
    print("\nDetaljert resultat:")
    print(json.dumps({"users": final_result["users"]}, indent=2))
    
    # Sjekk at vi har fått et resultat
    assert final_result is not None
    assert "users" in final_result
    assert len(final_result["users"]) > 0
    
    # Sjekk at CRM-integrasjonen har kjørt
    users_with_crm = [user for user in final_result["users"] if user.get("crm")]
    assert len(users_with_crm) > 0, "Ingen brukere har CRM-informasjon"
    
    # Sjekk at kontakter er opprettet
    contacts_created = [user for user in users_with_crm if user.get("crm", {}).get("contact_created")]
    assert len(contacts_created) > 0, "Ingen kontakter ble opprettet"
    
    # Sjekk at notater er opprettet
    notes_created = [user for user in users_with_crm if user.get("crm", {}).get("note_created")]
    assert len(notes_created) > 0, "Ingen notater ble opprettet"
    
    print(f"\nTest fullført: {len(contacts_created)} kontakter og {len(notes_created)} notater opprettet")
    
    # Returner resultatet for videre inspeksjon
    return final_result

if __name__ == "__main__":
    test_crm_integration() 