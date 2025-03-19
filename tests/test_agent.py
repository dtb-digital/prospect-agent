from langsmith import Client
import langsmith as ls
from agent import analyze_domain

client = Client()

# Definer tester
@ls.test(
    inputs={"domain": "example.com", "target_role": "sales"},
    reference_outputs={"num_users": 5}
)
def test_analyze_domain_returns_users(inputs, reference_outputs):
    """Test at analyze_domain returnerer brukere."""
    result = analyze_domain(inputs)
    ls.log_outputs(result)
    
    # Sjekk at resultatet inneholder brukere
    assert "users" in result
    assert len(result["users"]) > 0
    
    # Sjekk at antall brukere matcher forventet antall
    assert len(result["users"]) == reference_outputs["num_users"]

@ls.test.each([
    {"inputs": {"domain": "example.com", "target_role": "sales"}, "reference_outputs": {"has_analyzed": True}},
    {"inputs": {"domain": "test.com", "target_role": "marketing"}, "reference_outputs": {"has_analyzed": True}}
])
def test_analyze_domain_analyzes_users(inputs, reference_outputs):
    """Test at analyze_domain analyserer brukere."""
    result = analyze_domain(inputs)
    ls.log_outputs(result)
    
    # Sjekk at minst én bruker har blitt analysert
    analyzed_users = [u for u in result["users"] if "analyzed" in u.get("sources", [])]
    assert len(analyzed_users) > 0
    assert reference_outputs["has_analyzed"] == (len(analyzed_users) > 0) 