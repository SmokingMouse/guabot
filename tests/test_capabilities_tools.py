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


def test_default_registry_registers_bash_and_ls() -> None:
    registry: CapabilityRegistry = default_registry()
    names = registry.available_names()

    assert "shell.bash" in names
    assert "fs.ls" in names

