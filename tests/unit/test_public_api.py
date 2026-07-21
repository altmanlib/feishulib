from importlib.metadata import requires

import feishulib


def test_package_exposes_a_stable_version() -> None:
    assert feishulib.__version__ == "0.1.0"


def test_package_requires_the_generated_protobuf_runtime_range() -> None:
    package_requirements = requires("feishulib") or []

    assert any(
        requirement.replace(" ", "") == "protobuf>=7.35.0,<8"
        for requirement in package_requirements
    )
