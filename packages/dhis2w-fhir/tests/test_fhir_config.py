"""Unit tests for fhir.toml discovery, load, and save."""

from pathlib import Path

import pytest
from dhis2w_fhir.config import (
    FhirProjectConfig,
    GenerateConfig,
    IgConfig,
    IpsConfig,
    MalformedFhirConfigError,
    NoFhirProjectError,
    SearchBackend,
    SearchConfig,
    ServeAuth,
    ServeConfig,
    ServeJwtConfig,
    TrackedEntitiesConfig,
    UnknownFhirConfigKeyError,
    find_project_fhir_config,
    load_fhir_config,
    load_project,
    write_fhir_config,
)
from dhis2w_fhir.ips import IdentityNominations, ImmunizationsMapping, SectionMappings
from pydantic import ValidationError

_MINIMAL_TOML = """
[ig]
id = "dhis2.fhir.example"
canonical = "http://example.org/fhir/"
name = "Dhis2FhirExample"
title = "DHIS2 FHIR Example IG"
publisher = "Example Organisation"

[generate.organisation_units]
root = ""
max_level = 0
"""


def _make_config() -> FhirProjectConfig:
    """Build a minimal valid config."""
    return FhirProjectConfig(
        ig=IgConfig(
            id="dhis2.fhir.example",
            canonical="http://example.org/fhir",
            name="Dhis2FhirExample",
            title="DHIS2 FHIR Example IG",
            publisher="Example Organisation",
        )
    )


def test_find_walks_up(tmp_path: Path) -> None:
    """Discovery finds fhir.toml in a parent of the start directory."""
    (tmp_path / "fhir.toml").write_text(_MINIMAL_TOML, encoding="utf-8")
    nested = tmp_path / "ig" / "input" / "fsh"
    nested.mkdir(parents=True)
    assert find_project_fhir_config(nested) == tmp_path / "fhir.toml"


def test_find_returns_none_when_absent(tmp_path: Path) -> None:
    """Discovery returns None when no fhir.toml exists anywhere up the tree."""
    assert find_project_fhir_config(tmp_path) is None


def test_load_normalizes_placeholders(tmp_path: Path) -> None:
    """The scaffolded `root = \"\"` and `max_level = 0` placeholders load as None."""
    path = tmp_path / "fhir.toml"
    path.write_text(_MINIMAL_TOML, encoding="utf-8")
    config = load_fhir_config(path)
    assert config.generate.organisation_units.root is None
    assert config.generate.organisation_units.max_level is None
    assert config.ig.canonical == "http://example.org/fhir"


def test_round_trip(tmp_path: Path) -> None:
    """write_fhir_config -> load_fhir_config preserves the config."""
    path = tmp_path / "fhir.toml"
    config = _make_config()
    write_fhir_config(path, config)
    assert load_fhir_config(path) == config


def test_load_project_raises_without_config(tmp_path: Path) -> None:
    """load_project points the user at `d2w fhir init` when nothing is found."""
    with pytest.raises(NoFhirProjectError, match="d2w fhir init"):
        load_project(tmp_path)


def test_load_project_derives_directories(tmp_path: Path) -> None:
    """FhirProject exposes the project root and the ig/input/fsh directory."""
    (tmp_path / "fhir.toml").write_text(_MINIMAL_TOML, encoding="utf-8")
    project = load_project(tmp_path)
    assert project.project_root == tmp_path.resolve()
    assert project.fsh_directory == tmp_path.resolve() / "ig" / "input" / "fsh"


def test_data_definition_tables_parse(tmp_path: Path) -> None:
    """The three data-definition tables load as UID include lists, one per questionnaire form kind."""
    path = tmp_path / "fhir.toml"
    path.write_text(
        _MINIMAL_TOML
        + '\n[generate.data_sets]\ninclude_ids = ["BfMAe6Itzgt"]\n'
        + '\n[generate.event_programs]\ninclude_ids = ["VBqh0ynB2wv"]\n'
        + '\n[generate.tracker_programs]\ninclude_ids = ["IpHINAT79UW"]\n',
        encoding="utf-8",
    )
    config = load_fhir_config(path)
    assert config.generate.data_sets.include_ids == ["BfMAe6Itzgt"]
    assert config.generate.event_programs.include_ids == ["VBqh0ynB2wv"]
    assert config.generate.tracker_programs.include_ids == ["IpHINAT79UW"]


def test_tracker_program_selection_defaults_to_everything() -> None:
    """An absent `[generate.tracker_programs]` means every tracker program on the instance."""
    assert GenerateConfig().tracker_programs.include_ids == []


def test_questionnaire_naming_tokens_default_to_the_registry() -> None:
    """The data-set, program, and program-stage tokens default to DS / PR / PS, and may all be dropped."""
    assert GenerateConfig().naming.data_set == "DS"
    assert GenerateConfig().naming.program == "PR"
    assert GenerateConfig().naming.program_stage == "PS"
    assert GenerateConfig.model_validate({"naming": {"data_set": "", "program": ""}}).naming.data_set == ""
    assert GenerateConfig.model_validate({"naming": {"program_stage": ""}}).naming.program_stage == ""


def test_the_program_stage_token_is_overridable_and_validated() -> None:
    """A custom program-stage token lands in FSH names, so it takes the same letter-leading rule as its peers."""
    assert GenerateConfig.model_validate({"naming": {"program_stage": "Stage"}}).naming.program_stage == "Stage"
    with pytest.raises(ValidationError, match="letter-leading alphanumeric"):
        GenerateConfig.model_validate({"naming": {"program_stage": "2Stage"}})


def test_no_timezone_means_the_instances_timestamps_are_read_as_utc() -> None:
    """An absent `[generate] timezone` leaves DHIS2's zone-less timestamps read as UTC (BUGS.md #62)."""
    assert GenerateConfig().timezone is None


def test_a_named_timezone_must_be_an_iana_zone() -> None:
    """The zone stamps every emitted dateTime, so a name the tz database does not hold is a config error."""
    assert GenerateConfig(timezone="Asia/Vientiane").timezone == "Asia/Vientiane"
    with pytest.raises(ValidationError, match="unknown IANA time zone 'Asia/Vientianne'"):
        GenerateConfig(timezone="Asia/Vientianne")
    with pytest.raises(ValidationError, match="unknown IANA time zone '\\+07:00'"):
        GenerateConfig(timezone="+07:00")


def test_the_timezone_survives_a_config_round_trip(tmp_path: Path) -> None:
    """`[generate] timezone` is project config: it writes to fhir.toml and loads back off it."""
    path = tmp_path / "fhir.toml"
    config = _make_config()
    config.generate.timezone = "Europe/Oslo"
    write_fhir_config(path, config)
    assert load_fhir_config(path).generate.timezone == "Europe/Oslo"


def test_the_serve_table_defaults_to_loopback_and_lenient_codes() -> None:
    """An absent `[serve]` table serves on loopback port 8080 and warns rather than refuses unknown codes."""
    config = ServeConfig()
    assert config.host == "127.0.0.1"
    assert config.port == 8080
    assert config.strict_codes is False


def test_the_serve_table_parses_off_fhir_toml(tmp_path: Path) -> None:
    """Where a project is served from is project config, so it loads off the document like everything else."""
    path = tmp_path / "fhir.toml"
    path.write_text(
        """[ig]
id = "dhis2.fhir.test"
canonical = "http://example.org/fhir"
name = "TestIg"
title = "Test IG"
publisher = "Test Org"

[serve]
host = "0.0.0.0"
port = 8090
strict_codes = true
""",
        encoding="utf-8",
    )
    serve = load_fhir_config(path).serve
    assert serve.host == "0.0.0.0"
    assert serve.port == 8090
    assert serve.strict_codes is True


def test_locales_default_to_every_locale_found() -> None:
    """An absent `[generate] locales` means every translation locale on the instance is emitted."""
    assert GenerateConfig().locales == []


def test_locales_are_normalized_to_bcp47() -> None:
    """Java-style DHIS2 tags in fhir.toml are held in the BCP-47 form the emitters compare against."""
    assert GenerateConfig(locales=["pt_BR", "LO", "km"]).locales == ["pt-BR", "lo", "km"]


_IDENTITY_TOML = """
[ig]
id = "dhis2.fhir.example"
canonical = "http://example.org/fhir"
name = "Dhis2FhirExample"
title = "DHIS2 FHIR Example IG"
publisher = "Example Organisation"
"""


def _write(tmp_path: Path, *, before: str = "", after: str = "") -> Path:
    """A fhir.toml holding the identity table, with `before` above it and `after` below it."""
    path = tmp_path / "fhir.toml"
    path.write_text(before + _IDENTITY_TOML + after, encoding="utf-8")
    return path


def test_a_misspelled_key_is_refused_and_the_right_name_suggested(tmp_path: Path) -> None:
    """A misspelled option is named, placed in its table, and matched against what the table accepts."""
    path = _write(tmp_path, after='\n[generate.naming]\nprefx = "D2"\n')
    with pytest.raises(UnknownFhirConfigKeyError) as raised:
        load_fhir_config(path)
    assert raised.value.diagnostics == (
        "fhir.toml: unknown key 'prefx' in [generate.naming]\n  did you mean 'prefix'?",
    )


def test_a_misspelled_key_in_a_nested_section_names_that_section(tmp_path: Path) -> None:
    """The trap this refusal exists for: `max_lvl = 4` set nothing and said nothing."""
    path = _write(tmp_path, after="\n[generate.organisation_units]\nmax_lvl = 4\n")
    with pytest.raises(UnknownFhirConfigKeyError) as raised:
        load_fhir_config(path)
    assert raised.value.diagnostics == (
        "fhir.toml: unknown key 'max_lvl' in [generate.organisation_units]\n  did you mean 'max_level'?",
    )


def test_a_key_resembling_nothing_is_refused_without_a_suggestion(tmp_path: Path) -> None:
    """A guess would be worse than none: an unknown key with no near neighbour is reported on its own."""
    path = _write(tmp_path, after='\n[serve]\nlisten_on_every_interface = "0.0.0.0"\n')
    with pytest.raises(UnknownFhirConfigKeyError) as raised:
        load_fhir_config(path)
    assert raised.value.diagnostics == ("fhir.toml: unknown key 'listen_on_every_interface' in [serve]",)


def test_a_misspelled_top_level_key_is_placed_at_the_top_of_the_file(tmp_path: Path) -> None:
    """A key outside every table has no section name to be reported under, so it is placed by where it sits."""
    path = _write(tmp_path, before='profil = "myserver"\n')
    with pytest.raises(UnknownFhirConfigKeyError) as raised:
        load_fhir_config(path)
    assert raised.value.diagnostics == (
        "fhir.toml: unknown key 'profil' at the top level of the file\n  did you mean 'profile'?",
    )


def test_every_unknown_key_is_reported_in_one_pass(tmp_path: Path) -> None:
    """One run names every misspelling, so the file is fixed in one edit rather than one command per key."""
    path = _write(
        tmp_path,
        after='\n[generate]\nidentifier_system_bases = "http://example.org"\n'
        "\n[generate.organisation_units]\nmax_lvl = 4\n"
        "\n[serve]\nstrict_code = true\n",
    )
    with pytest.raises(UnknownFhirConfigKeyError) as raised:
        load_fhir_config(path)
    assert raised.value.diagnostics == (
        "fhir.toml: unknown key 'identifier_system_bases' in [generate]\n  did you mean 'identifier_system_base'?",
        "fhir.toml: unknown key 'max_lvl' in [generate.organisation_units]\n  did you mean 'max_level'?",
        "fhir.toml: unknown key 'strict_code' in [serve]\n  did you mean 'strict_codes'?",
    )


def test_a_selection_table_refuses_unknown_keys_too(tmp_path: Path) -> None:
    """Every table of the document forbids what it does not declare, the selection tables included."""
    path = _write(tmp_path, after='\n[generate.data_sets]\ninclude_id = ["BfMAe6Itzgt"]\n')
    with pytest.raises(UnknownFhirConfigKeyError) as raised:
        load_fhir_config(path)
    assert raised.value.diagnostics == (
        "fhir.toml: unknown key 'include_id' in [generate.data_sets]\n  did you mean 'include_ids'?",
    )


def test_a_wrong_value_keeps_the_pydantic_report(tmp_path: Path) -> None:
    """A refusal about a value is not a refusal about a name: it keeps the report naming the accepted values."""
    path = _write(tmp_path, after='\n[generate.naming]\nprefix = "2D"\n')
    with pytest.raises(ValidationError, match="letter-leading alphanumeric"):
        load_fhir_config(path)


def test_a_tracked_entity_type_map_still_takes_any_uid_as_a_key(tmp_path: Path) -> None:
    """The one table whose keys are DHIS2 UIDs rather than option names keeps taking whatever the instance holds."""
    path = _write(tmp_path, after='\n[generate.tracked_entity_types]\n"Kd6Nk9wnAJa" = "Group"\n')
    assert load_fhir_config(path).generate.tracked_entity_types == {"Kd6Nk9wnAJa": "Group"}


def test_the_tracked_entities_table_serves_a_listing_of_twenty_by_default() -> None:
    """An absent `[serve.tracked_entities]` serves people, lists them, records them, and pages twenty at a time."""
    tracked_entities = ServeConfig().tracked_entities

    assert tracked_entities.enabled is True
    assert tracked_entities.listing is True
    assert tracked_entities.events is True
    assert tracked_entities.page_size == 20
    assert tracked_entities.page_size_limit == 100
    assert tracked_entities.tracked_entity_types == []
    assert tracked_entities.search_attributes == []


def test_the_tracked_entities_table_parses_off_fhir_toml(tmp_path: Path) -> None:
    """What a live run says about people is project config, so it loads off the document like the rest."""
    path = _write(
        tmp_path,
        after="\n[serve.tracked_entities]\nenabled = true\nlisting = false\nevents = false\npage_size = 5\n"
        "page_size_limit = 50\n"
        'tracked_entity_types = ["nEenWmSyUEp"]\nsearch_attributes = ["lZGmxYbs97q"]\n',
    )

    tracked_entities = load_fhir_config(path).serve.tracked_entities

    assert tracked_entities.listing is False
    assert tracked_entities.events is False
    assert tracked_entities.page_size == 5
    assert tracked_entities.page_size_limit == 50
    assert tracked_entities.tracked_entity_types == ["nEenWmSyUEp"]
    assert tracked_entities.search_attributes == ["lZGmxYbs97q"]


def test_the_search_table_answers_a_lookup_from_the_instance_by_default() -> None:
    """An absent `[serve.search]` is the search a live run has always run: the instance itself, exactly."""
    assert ServeConfig().search.backend is SearchBackend.DHIS2
    assert SearchConfig().backend is SearchBackend.DHIS2


def test_the_search_table_parses_off_fhir_toml(tmp_path: Path) -> None:
    """What answers a register search is project config, so it loads off the document like the rest."""
    path = _write(tmp_path, after='\n[serve.search]\nbackend = "dhis2"\n')

    assert load_fhir_config(path).serve.search == SearchConfig(backend=SearchBackend.DHIS2)


def test_a_backend_this_server_holds_no_index_for_is_refused_by_name(tmp_path: Path) -> None:
    """`"index"` arrives with the OpenSearch backend; until then the key refuses it and says where it refused.

    A value that parses and then finds nothing to run on is worse than one the file turns down, so
    the refusal is pydantic's own report, naming `serve.search.backend` and the words it accepts.
    """
    path = _write(tmp_path, after='\n[serve.search]\nbackend = "index"\n')

    with pytest.raises(ValidationError) as refused:
        load_fhir_config(path)

    assert refused.value.errors()[0]["loc"] == ("serve", "search", "backend")
    assert "'dhis2'" in str(refused.value)


def test_a_misspelled_key_in_the_search_table_gets_the_same_treatment(tmp_path: Path) -> None:
    """`[serve.search]` declares its full key set like every other table, so a typo is named and placed."""
    path = _write(tmp_path, after='\n[serve.search]\nbackends = "dhis2"\n')

    with pytest.raises(UnknownFhirConfigKeyError) as raised:
        load_fhir_config(path)

    assert raised.value.diagnostics == (
        "fhir.toml: unknown key 'backends' in [serve.search]\n  did you mean 'backend'?",
    )


def test_the_search_table_survives_a_config_round_trip(tmp_path: Path) -> None:
    """The table writes to fhir.toml and loads back off it, the way every `[serve]` sub-table does."""
    path = tmp_path / "fhir.toml"
    config = _make_config()
    config.serve = ServeConfig(search=SearchConfig(backend=SearchBackend.DHIS2))

    write_fhir_config(path, config)

    assert load_fhir_config(path).serve.search == SearchConfig(backend=SearchBackend.DHIS2)


def test_a_page_carries_at_least_one_tracked_entity() -> None:
    """A page of nobody is a listing whose `next` link never reaches the end of the register."""
    with pytest.raises(ValidationError, match="a page carries at least one tracked entity"):
        TrackedEntitiesConfig(page_size=0)


def test_the_page_size_limit_cannot_be_smaller_than_the_page_served_by_default() -> None:
    """The limit is the largest page this server serves, so a default above it could never be served."""
    assert TrackedEntitiesConfig(page_size=50, page_size_limit=50).page_size_limit == 50
    with pytest.raises(ValidationError, match="cannot be smaller than the page it serves by default"):
        TrackedEntitiesConfig(page_size=50, page_size_limit=20)


def test_the_register_scoping_lists_name_dhis2_objects_by_uid() -> None:
    """A name or a code in either list would select nothing, silently, so the shape is checked here."""
    with pytest.raises(ValidationError, match="is not a DHIS2 UID"):
        TrackedEntitiesConfig(tracked_entity_types=["Person"])
    with pytest.raises(ValidationError, match="is not a DHIS2 UID"):
        TrackedEntitiesConfig(search_attributes=["NATIONAL_ID"])


def test_a_misspelled_key_in_the_tracked_entities_table_gets_the_same_treatment(tmp_path: Path) -> None:
    """`[serve.tracked_entities]` declares its full key set like every other table, so a typo is named and placed."""
    path = _write(tmp_path, after="\n[serve.tracked_entities]\npage_sizes = 40\n")

    with pytest.raises(UnknownFhirConfigKeyError) as raised:
        load_fhir_config(path)

    assert raised.value.diagnostics == (
        "fhir.toml: unknown key 'page_sizes' in [serve.tracked_entities]\n  did you mean 'page_size'?",
    )


def test_the_tracked_entities_table_survives_a_config_round_trip(tmp_path: Path) -> None:
    """The table writes to fhir.toml and loads back off it, nested tables included."""
    path = tmp_path / "fhir.toml"
    config = _make_config()
    config.serve = ServeConfig(tracked_entities=TrackedEntitiesConfig(listing=False, page_size=10))

    write_fhir_config(path, config)

    assert load_fhir_config(path).serve.tracked_entities == TrackedEntitiesConfig(listing=False, page_size=10)


def test_the_jwt_table_defaults_to_the_openid_connect_convention_and_no_forwarding() -> None:
    """A project stating only an issuer gets the standard username claim and no token sent to DHIS2."""
    table = ServeJwtConfig(issuer="https://idp.example.org/realms/health")

    assert table.username_claim == "preferred_username"
    assert table.audience is None
    assert table.forward_bearer is False


def test_an_absent_jwt_table_is_a_table_of_defaults_naming_no_issuer() -> None:
    """The posture refuses by the key's name rather than by a missing section, which needs the table present."""
    assert ServeConfig().jwt.issuer is None


def test_a_trailing_slash_on_the_issuer_is_dropped_so_one_issuer_is_one_string() -> None:
    """A token's `iss` carries no trailing slash, and the comparison is a string comparison."""
    assert ServeJwtConfig(issuer="https://idp.example.org/realms/health/").issuer == (
        "https://idp.example.org/realms/health"
    )


def test_a_blank_issuer_states_nothing_rather_than_naming_an_empty_one() -> None:
    """`issuer = ""` and an absent key mean the same thing, and both are refused by the preflight."""
    assert ServeJwtConfig(issuer="  ").issuer is None


def test_an_issuer_that_is_not_a_url_is_refused_by_name() -> None:
    """The issuer is what `/.well-known/openid-configuration` is appended to, so it has to be a URL."""
    with pytest.raises(ValidationError, match="is not an issuer identifier"):
        ServeJwtConfig(issuer="idp.example.org")


def test_a_blank_username_claim_would_read_every_token_as_naming_nobody() -> None:
    """A claim name has to name a claim; leaving the key out is how a project takes the default."""
    with pytest.raises(ValidationError, match="username_claim is empty"):
        ServeJwtConfig(username_claim="   ")


def test_the_jwt_table_parses_off_fhir_toml(tmp_path: Path) -> None:
    """Which issuer a deployment federates with is project config, so it loads off the document."""
    path = _write(
        tmp_path,
        after=(
            '\n[serve]\nauth = "jwt"\n\n[serve.jwt]\n'
            'issuer = "https://idp.example.org/realms/health"\n'
            'audience = "d2w-fhir-serve"\n'
            'username_claim = "dhis2_username"\n'
            "forward_bearer = true\n"
        ),
    )

    serve = load_fhir_config(path).serve

    assert serve.auth is ServeAuth.JWT
    assert serve.jwt.issuer == "https://idp.example.org/realms/health"
    assert serve.jwt.audience == "d2w-fhir-serve"
    assert serve.jwt.username_claim == "dhis2_username"
    assert serve.jwt.forward_bearer is True


def test_a_misspelled_key_in_the_jwt_table_gets_the_same_treatment(tmp_path: Path) -> None:
    """`[serve.jwt]` declares its full key set like every other table, so a typo is named and placed."""
    path = _write(tmp_path, after='\n[serve.jwt]\nissur = "https://idp.example.org"\n')

    with pytest.raises(UnknownFhirConfigKeyError) as raised:
        load_fhir_config(path)

    assert raised.value.diagnostics == ("fhir.toml: unknown key 'issur' in [serve.jwt]\n  did you mean 'issuer'?",)


def test_the_jwt_table_survives_a_config_round_trip(tmp_path: Path) -> None:
    """The table writes to fhir.toml and loads back off it, exactly as its sibling tables do."""
    path = tmp_path / "fhir.toml"
    config = _make_config()
    config.serve = ServeConfig(
        auth=ServeAuth.JWT,
        jwt=ServeJwtConfig(issuer="https://idp.example.org/realms/health", audience="d2w-fhir-serve"),
    )

    write_fhir_config(path, config)

    assert load_fhir_config(path).serve.jwt == ServeJwtConfig(
        issuer="https://idp.example.org/realms/health", audience="d2w-fhir-serve"
    )


def test_a_malformed_fhir_toml_is_a_worded_refusal_naming_the_file(tmp_path: Path) -> None:
    """Invalid TOML answers with the file and the parser's own location, never a raw traceback."""
    config_path = tmp_path / "fhir.toml"
    config_path.write_text("[serve]\nui = true\n[serve]\nui = false\n", encoding="utf-8")
    with pytest.raises(MalformedFhirConfigError) as raised:
        load_fhir_config(config_path)
    message = str(raised.value)
    assert str(config_path) in message
    assert "not valid TOML" in message


_IDENTITY_TABLE = (
    "\n[ips.identity]\n"
    'name = "w75KJ2mc4zz"\n'
    'birth_date = "iESIqZ0R0R0"\n'
    'sex = "cejWyOfXge6"\n'
    "\n[ips.identity.administrative_gender]\n"
    '"Male" = "male"\n'
    '"Female" = "female"\n'
)


def test_the_identity_table_parses_off_fhir_toml(tmp_path: Path) -> None:
    """Which attribute means what is the instance's own statement, so it loads off the document."""
    path = _write(tmp_path, after=_IDENTITY_TABLE)

    identity = load_fhir_config(path).ips.identity

    assert identity.name == "w75KJ2mc4zz"
    assert identity.birth_date == "iESIqZ0R0R0"
    assert identity.sex == "cejWyOfXge6"
    assert identity.administrative_gender == {"Male": "male", "Female": "female"}
    assert identity.nominates_anything() is True


def test_a_project_stating_no_identity_table_nominates_nothing(tmp_path: Path) -> None:
    """An absent table is the whole of what every project written before it said: nominate nothing."""
    identity = load_fhir_config(_write(tmp_path)).ips.identity

    assert identity == IdentityNominations()
    assert identity.nominates_anything() is False
    assert identity.nominated_attribute_uids() == ()


def test_a_nomination_that_is_not_a_uid_is_refused_by_the_shape(tmp_path: Path) -> None:
    """A name or a code here would nominate nothing, silently, so the file refuses anything but a UID."""
    path = _write(tmp_path, after='\n[ips.identity]\nname = "First name"\n')

    with pytest.raises(ValidationError) as raised:
        load_fhir_config(path)

    assert "is not a DHIS2 UID" in str(raised.value)


def test_a_gender_outside_the_four_r4_codes_is_refused_by_name(tmp_path: Path) -> None:
    """`Patient.gender` has a required binding, so a fifth word maps onto nothing a client can read."""
    path = _write(
        tmp_path,
        after='\n[ips.identity]\nsex = "cejWyOfXge6"\n\n[ips.identity.administrative_gender]\n"M" = "man"\n',
    )

    with pytest.raises(ValidationError) as raised:
        load_fhir_config(path)

    assert "administrative-gender codes" in str(raised.value)


def test_a_nominated_sex_with_no_map_is_refused(tmp_path: Path) -> None:
    """A sex nomination whose values map onto nothing publishes no gender at all, which nobody asked for."""
    path = _write(tmp_path, after='\n[ips.identity]\nsex = "cejWyOfXge6"\n')

    with pytest.raises(ValidationError) as raised:
        load_fhir_config(path)

    assert "maps nothing" in str(raised.value)


def test_a_gender_map_with_no_nominated_sex_is_refused(tmp_path: Path) -> None:
    """The map names values of an attribute nobody nominated, so the file says which half is missing."""
    path = _write(tmp_path, after='\n[ips.identity.administrative_gender]\n"Male" = "male"\n')

    with pytest.raises(ValidationError) as raised:
        load_fhir_config(path)

    assert "an attribute nobody nominated" in str(raised.value)


def test_a_misspelled_key_in_the_identity_table_gets_the_same_treatment(tmp_path: Path) -> None:
    """`[ips.identity]` declares its full key set like every other table, so a typo is named and placed."""
    path = _write(tmp_path, after='\n[ips.identity]\nbirthdate = "iESIqZ0R0R0"\n')

    with pytest.raises(UnknownFhirConfigKeyError) as raised:
        load_fhir_config(path)

    assert raised.value.diagnostics == (
        "fhir.toml: unknown key 'birthdate' in [ips.identity]\n  did you mean 'birth_date'?",
    )


def test_a_misspelled_key_in_the_ips_table_gets_the_same_treatment(tmp_path: Path) -> None:
    """The `[ips]` table declares what it declares, and refuses the name of a key nobody built."""
    path = _write(tmp_path, after="\n[ips]\nenable = true\n")

    with pytest.raises(UnknownFhirConfigKeyError) as raised:
        load_fhir_config(path)

    assert raised.value.diagnostics == ("fhir.toml: unknown key 'enable' in [ips]\n  did you mean 'enabled'?",)


def test_the_sections_table_refuses_a_section_nobody_mapped(tmp_path: Path) -> None:
    """`[ips.sections]` declares one section today, and a project naming another is told the key is not one."""
    path = _write(tmp_path, after='\n[ips.sections.problems]\ndata_elements = ["a3kGcGDCuk6"]\n')

    with pytest.raises(UnknownFhirConfigKeyError) as raised:
        load_fhir_config(path)

    assert raised.value.diagnostics == ("fhir.toml: unknown key 'problems' in [ips.sections]",)


def test_the_immunizations_table_refuses_a_stage_with_no_data_element(tmp_path: Path) -> None:
    """One list without the other maps no dose, so the file refuses the pair broken."""
    path = _write(tmp_path, after='\n[ips.sections.immunizations]\nprogram_stages = ["A03MvHHogjR"]\n')

    with pytest.raises(ValidationError) as raised:
        load_fhir_config(path)

    assert "dose_data_elements names no data element" in str(raised.value)


def test_the_immunizations_table_refuses_a_data_element_that_is_not_a_uid(tmp_path: Path) -> None:
    """Every nomination names a DHIS2 object by UID; a name here would nominate nothing."""
    path = _write(
        tmp_path,
        after=(
            '\n[ips.sections.immunizations]\nprogram_stages = ["A03MvHHogjR"]\ndose_data_elements = ["MCH BCG dose"]\n'
        ),
    )

    with pytest.raises(ValidationError) as raised:
        load_fhir_config(path)

    assert "is not a DHIS2 UID" in str(raised.value)


def test_the_sections_table_survives_a_config_round_trip(tmp_path: Path) -> None:
    """The section mapping writes to fhir.toml and loads back off it, exactly as the identity table does."""
    path = tmp_path / "fhir.toml"
    config = _make_config()
    config.ips = IpsConfig(
        enabled=True,
        sections=SectionMappings(
            immunizations=ImmunizationsMapping(
                program_stages=("A03MvHHogjR", "ZzYYXq4fJie"),
                dose_data_elements=("bx6fsa0t90x", "FqlgKAG8HOu"),
            )
        ),
    )

    write_fhir_config(path, config)

    assert load_fhir_config(path).ips == config.ips


def test_the_identity_table_survives_a_config_round_trip(tmp_path: Path) -> None:
    """The table writes to fhir.toml and loads back off it, exactly as its sibling tables do."""
    path = tmp_path / "fhir.toml"
    config = _make_config()
    config.ips = IpsConfig(
        identity=IdentityNominations(
            name="w75KJ2mc4zz", sex="cejWyOfXge6", administrative_gender={"Male": "male", "Female": "female"}
        )
    )

    write_fhir_config(path, config)

    assert load_fhir_config(path).ips == config.ips
