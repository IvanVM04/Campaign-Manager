import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOUNDARIES = {
    "models": {"api", "services"},
    "operations": {"api", "services", "repositories"},
    "rules_engine": {"api", "models", "services", "repositories"},
    "repositories": {"api", "services"},
    "services": {"api"},
}


def _import_roots(source: str) -> set[str]:
    tree = ast.parse(source)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".", maxsplit=1)[0])
    return roots


def test_core_layers_do_not_import_inward_or_sideways():
    violations = []

    for layer, forbidden_roots in BOUNDARIES.items():
        layer_path = ROOT / layer
        if not layer_path.is_dir():
            continue
        for path in sorted(layer_path.rglob("*.py")):
            imports = _import_roots(path.read_text(encoding="utf-8"))
            forbidden = sorted(imports & forbidden_roots)
            if forbidden:
                violations.append(
                    f"{path.relative_to(ROOT)} imports forbidden layer(s): "
                    f"{', '.join(forbidden)}"
                )

    assert not violations, (
        "Architectural dependency boundaries were violated:\n"
        + "\n".join(violations)
    )



# Capability-package rules are intentionally expressed as forbidden edges:
# new dependencies require an explicit architecture decision and a test update.
PACKAGE_FORBIDDEN_IMPORTS = {
    "campaign": {
        "api",
        "bootstrap",
        "services.characters",
        "services.combat",
        "services.context",
        "services.llm_world",
        "services.providers",
        "services.turns",
    },
    "characters": {
        "api",
        "bootstrap",
        "services.campaign",
        "services.combat",
        "services.context",
        "services.llm_world",
        "services.providers",
        "services.turns",
        "services.world",
    },
    "combat": {
        "api",
        "bootstrap",
        "services.campaign",
        "services.context",
        "services.llm_world",
        "services.providers",
        "services.turns",
        "services.world",
    },
    "context": {
        "api",
        "bootstrap",
        "services.campaign",
        "services.characters",
        "services.combat",
        "services.memory_search_service",
        "services.llm_world",
        "services.providers",
        "services.turns",
    },
    "llm_world": {
        "api",
        "bootstrap",
        "database",
        "repositories",
        "services.campaign",
        "services.characters",
        "services.combat",
        "services.context",
        "services.providers",
        "services.turns",
        "services.world",
    },
    "providers": {
        "api",
        "bootstrap",
        "database",
        "models",
        "operations",
        "repositories",
        "rules_engine",
        "services",
    },
    "turns": {
        "api",
        "bootstrap",
    },
    "world": {
        "api",
        "bootstrap",
        "services.campaign",
        "services.combat",
        "services.context",
        "services.llm_world",
        "services.providers",
        "services.turns",
    },
}


def _absolute_module_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module)
    return imports

def _context_module_imports(source: str) -> set[str]:
    """Resolve one-dot imports from services.context to canonical module names."""
    imports = _absolute_module_imports(source)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
            imports.add(f"services.context.{node.module}")
    return imports


def test_capability_packages_respect_dependency_matrix():
    violations = []

    for package, forbidden_modules in PACKAGE_FORBIDDEN_IMPORTS.items():
        package_path = ROOT / "services" / package
        for path in sorted(package_path.rglob("*.py")):
            imports = _absolute_module_imports(path.read_text(encoding="utf-8"))
            forbidden = sorted(
                imported
                for imported in imports
                if any(
                    imported == blocked or imported.startswith(blocked + ".")
                    for blocked in forbidden_modules
                )
            )
            if forbidden:
                violations.append(
                    f"{path.relative_to(ROOT)} imports forbidden module(s): "
                    f"{', '.join(forbidden)}"
                )

    assert not violations, (
        "Capability-package dependency matrix was violated:\n"
        + "\\n".join(violations)
    )


def test_capability_services_do_not_depend_on_external_adapters():
    violations = []
    services_path = ROOT / "services"
    for path in sorted(services_path.rglob("*.py")):
        imports = _absolute_module_imports(path.read_text(encoding="utf-8"))
        external = sorted(
            imported
            for imported in imports
            if imported == "integrations" or imported.startswith("integrations.")
        )
        if external:
            violations.append(
                f"{path.relative_to(ROOT)} imports external adapter(s): "
                f"{', '.join(external)}"
            )
    assert not violations, (
        "Capability services must not depend on external integration adapters:\\n"
        + "\\n".join(violations)
    )


def test_external_silly_tavern_adapters_do_not_import_transport_or_composition():
    violations = []
    adapter_path = ROOT / "integrations" / "adapters" / "silly_tavern"
    for path in sorted(adapter_path.rglob("*.py")):
        imports = _import_roots(path.read_text(encoding="utf-8"))
        forbidden = sorted(imports & {"api", "bootstrap"})
        if forbidden:
            violations.append(
                f"{path.relative_to(ROOT)} imports forbidden layer(s): "
                f"{', '.join(forbidden)}"
            )
    assert not violations, (
        "External integration adapters must not depend on API or bootstrap:\\n"
        + "\\n".join(violations)
    )


# Discourse collaborators are intentionally decomposed behind a stable facade.
DISCOURSE_COMPONENTS = {
    "contracts.py": set(),
    "text.py": set(),
    "speech_predicates.py": set(),
    "topic_history_selector.py": {
        "services.discourse.contracts",
        "services.discourse.text",
    },
    "surface_mention_extractor.py": {
        "services.discourse.contracts",
        "services.discourse.text",
    },
    "speaker_signal_extractor.py": {
        "services.discourse.contracts",
        "services.discourse.surface_mention_extractor",
        "services.discourse.speech_predicates",
    },
    "renderer.py": {
        "services.discourse.topic_history_selector",
        "services.discourse.surface_mention_extractor",
        "services.discourse.speaker_signal_extractor",
    },
}


def test_discourse_collaborators_follow_the_declared_dependency_direction():
    package = ROOT / "services" / "discourse"
    violations = []
    for filename, allowed in DISCOURSE_COMPONENTS.items():
        path = package / filename
        imports = _absolute_module_imports(path.read_text(encoding="utf-8"))
        discourse_imports = {
            imported for imported in imports
            if imported.startswith("services.discourse.")
        }
        unexpected = sorted(discourse_imports - allowed)
        if unexpected:
            violations.append(
                f"{path.relative_to(ROOT)} imports unexpected discourse modules: "
                + ", ".join(unexpected)
            )
    assert not violations, (
        "Discourse collaborator dependency direction was violated:\\n"
        + "\\n".join(violations)
    )


def test_discourse_collaborators_do_not_import_the_public_facade():
    package = ROOT / "services" / "discourse"
    offenders = [
        path.name
        for path in sorted(package.glob("*.py"))
        if "services.discourse_context" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        "Discourse collaborators must not import their public facade: "
        + ", ".join(offenders)
    )


# Conversation-reference collaborators have explicit one-way dependencies.
def test_conversation_reference_evidence_and_ranking_have_single_owners():
    package = ROOT / "services" / "context"
    evidence_path = package / "conversation_reference_evidence.py"
    ranker_path = package / "conversation_reference_ranker.py"
    resolver_path = package / "conversation_reference_resolver.py"

    evidence_imports = _context_module_imports(
        evidence_path.read_text(encoding="utf-8")
    )
    ranker_imports = _context_module_imports(
        ranker_path.read_text(encoding="utf-8")
    )
    resolver_imports = _context_module_imports(
        resolver_path.read_text(encoding="utf-8")
    )

    assert "services.context.conversation_reference_resolver" not in evidence_imports
    assert "services.context.conversation_reference_ranker" not in evidence_imports
    assert "services.context.conversation_reference_resolver" not in ranker_imports
    assert "services.context.conversation_reference_evidence" not in ranker_imports
    assert "services.context.conversation_reference_evidence" in resolver_imports
    assert "services.context.conversation_reference_ranker" in resolver_imports

    model_imports = _absolute_module_imports(
        (ROOT / "models" / "discourse_evidence.py").read_text(encoding="utf-8")
    )
    assert not {
        imported
        for imported in model_imports
        if imported == "services" or imported.startswith("services.")
    }

def test_v3_semantic_contract_is_not_wired_into_production_services_or_bootstrap():
    forbidden = "models.player_turn_interpretation_v3"
    violations = []
    for layer in ("services", "bootstrap"):
        layer_path = ROOT / layer
        if not layer_path.exists():
            continue
        for path in sorted(layer_path.rglob("*.py")):
            imports = _absolute_module_imports(path.read_text(encoding="utf-8"))
            if any(
                imported == forbidden or imported.startswith(forbidden + ".")
                for imported in imports
            ):
                violations.append(str(path.relative_to(ROOT)))
    assert not violations, (
        "V3 contract must remain additive and isolated before PR #286: "
        + ", ".join(violations)
    )
