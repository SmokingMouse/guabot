from guabot.capabilities import BashCapability, CapabilityRegistry, LsCapability, default_registry


def test_bash_capability_echo() -> None:
    bash = BashCapability()
    result = bash.invoke({"cmd": "echo hello-tools"})

    assert result["exit_code"] == 0
    assert "hello-tools" in result["stdout"]


def test_ls_capability_lists_current_directory() -> None:
    ls = LsCapability()
    result = ls.invoke({"path": "."})

    assert "entries" in result
    assert isinstance(result["entries"], list)


def test_default_registry_registers_tools_and_skills() -> None:
    registry: CapabilityRegistry = default_registry()
    names = registry.available_names()

    assert "shell.bash" in names
    assert "fs.ls" in names
    assert "skill.error_count" in names
    assert "skill.version_info" in names


def test_registry_exposes_capability_descriptors() -> None:
    registry: CapabilityRegistry = default_registry()
    descriptors = registry.available_descriptors(llm_only=True)

    by_name = {item["name"]: item for item in descriptors}
    assert by_name["shell.bash"]["kind"] == "tool"
    assert by_name["skill.error_count"]["kind"] == "skill"
