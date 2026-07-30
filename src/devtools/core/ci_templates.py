"""Ready-made CI configs for `devtools ci init` (spec §10-ish: "CI/enterprise
integration" weakness called out in the transformation proposal).

Templates just shell out to `devtools` itself with the exit-code hooks that
already exist (`doctor --ci`, `deps --check`, `license-check --check`) —
nothing new to maintain on the CI side, this only wires up what's already
there.
"""

from __future__ import annotations

_GITHUB_ACTIONS_TEMPLATE = """\
name: devtools checks

on:
  push:
    branches: [main]
  pull_request:

jobs:
  devtools:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install devtools
        run: pip install devtools
      - name: devtools project add
        run: devtools project add {project_name} . --force
      - name: devtools doctor --ci
        run: devtools doctor {project_name} --ci
      - name: devtools deps --check
        run: devtools deps {project_name} --check
"""

_GITLAB_CI_TEMPLATE = """\
devtools:
  image: python:3.12
  stage: test
  script:
    - pip install devtools
    - devtools project add {project_name} . --force
    - devtools doctor {project_name} --ci
    - devtools deps {project_name} --check
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
"""

TEMPLATES = {
    "github": {
        "path": ".github/workflows/devtools.yml",
        "render": lambda project_name: _GITHUB_ACTIONS_TEMPLATE.format(project_name=project_name),
    },
    "gitlab": {
        "path": ".gitlab-ci.yml",
        "render": lambda project_name: _GITLAB_CI_TEMPLATE.format(project_name=project_name),
    },
}


def render_ci_config(provider: str, project_name: str) -> tuple[str, str]:
    """Return (relative_output_path, rendered_config_text) for `provider`.

    Raises ValueError for an unrecognized provider (callers turn this into a
    normal CLI usage error rather than a traceback).
    """
    template = TEMPLATES.get(provider)
    if template is None:
        raise ValueError(f"Unknown CI provider {provider!r}. Supported: {', '.join(sorted(TEMPLATES))}.")
    return template["path"], template["render"](project_name)
