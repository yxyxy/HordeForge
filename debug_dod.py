from agents.dod_extractor import DodExtractor, generate_bdd_from_ac, parse_issue, validate_contract

# Test with empty issue
print("Testing with empty issue...")
context = {"issue": {}}
print(f"Context: {context}")
issue = context.get("issue")
print(f"Issue: {issue}")
print(f"Issue is truthy: {bool(issue)}")

parsed = parse_issue(issue)
print(f"Parsed: {parsed}")
print(f"Parsed acceptance_criteria: {parsed.acceptance_criteria}")

# Simulate the logic
ac = parsed.acceptance_criteria
print(f"AC: {ac}")
print(f"AC is truthy: {bool(ac)}")

if ac:
    print("Using AC from issue")
    bdd = generate_bdd_from_ac(ac)
else:
    print("No AC found, using defaults")
    ac = ["Feature described in issue works as expected"]
    bdd = generate_bdd_from_ac(ac)
    method = "default_fallback"

print(f"Final AC: {ac}")
print(f"Final BDD: {bdd}")

artifact = {
    "schema_version": "1.0",
    "title": parsed.title,
    "acceptance_criteria": ac,
    "bdd_scenarios": bdd,
    "extraction_method": method if "method" in locals() else "unknown",
}

print(f"Artifact: {artifact}")
print(f"Validation result: {validate_contract(artifact)}")

# Now test the full agent
print("\nTesting full agent...")
agent = DodExtractor()
result = agent.run(context)
print("Result:", result)
print("Status:", result.get("status"))
print("Artifact content:", result.get("artifact_content"))
