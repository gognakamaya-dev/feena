import pytest

from feena.hosted_pilot import hosted_environment


def test_render_identity_is_operator_supplied():
    source = {"FEENA_MCP_TOKEN": "x" * 40, "RENDER_EXTERNAL_HOSTNAME": "feena-123.onrender.com"}
    env = hosted_environment(source)
    assert env["FEENA_MCP_PUBLIC_URL"] == "https://feena-123.onrender.com/mcp"
    assert env["FEENA_MCP_HOSTS"] == "feena-123.onrender.com"
    assert "FEENA_MCP_PUBLIC_URL" not in source


@pytest.mark.parametrize("host", ["", "evil.example", "a.onrender.com/path", "a.onrender.com:443",
                                  "a.onrender.com,evil.example"])
def test_reject_invalid_render_hostname(host):
    with pytest.raises(ValueError, match="hostname"):
        hosted_environment({"FEENA_MCP_TOKEN": "x" * 40, "RENDER_EXTERNAL_HOSTNAME": host})


def test_pilot_requires_secret():
    with pytest.raises(ValueError, match="TOKEN"):
        hosted_environment({"RENDER_EXTERNAL_HOSTNAME": "feena.onrender.com"})
