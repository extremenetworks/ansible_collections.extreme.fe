Hi team — approving the direction with conditions to keep the Galaxy artifact clean and CI maintainable.

1) Packaging Exclusions — confirm and validate
- Confirm build_ignore in galaxy.yml excludes internal content:
  - .git/, .github/**, .venv/, venv/, .tox/, tests/ (and subpaths), scripts/, dist/
  - Reference: ansible_collections/extreme/fe/galaxy.yml
- Acceptance:
  - Fresh build shows no test or CI files inside the tar (only directory markers at most):
    - tar -tf dist/extreme-fe-1.0.0.tar.gz | grep -E "^(tests/|\\.github/)"
  - Local install of the tar succeeds without referencing test assets.

2) Documentation — update to reflect harness changes
- Add a short entry in CHANGELOG.md noting harness rework and CI workflow addition (no user-facing module changes).
- Update any docs referencing removed/renamed files (e.g., software_install.sh) to point to current templates and scripts:
  - Docs: ansible_collections/extreme/fe/docs
- Consider a short “Internal Harness Quickstart” in docs/development describing inventory/interface templates, start/stop scripts, and Docker helpers.

3) Lint Scope — contain noise from tests
- Flake8: exclude tests from repo lint to avoid harness noise:
  - Updated: ansible_collections/extreme/fe/.flake8
  - Exclude tests/, and per-file ignores for tests/**/*.py: E501,E402 as needed
- Ansible-lint: exclude tests/ and .github/ from production profile runs:
  - Updated: ansible_collections/extreme/fe/.ansible-lint
- Optional: add a CI job/pre-commit that lint-checks only collection code (plugins/, module_utils/, httpapi/), and keeps playbooks/testing out of “production” lint scope.

4) CI Workflow — visibility and usage
- Ensure publish-galaxy.yml is merged to main so Actions shows the workflow:
  - .github/workflows/publish-galaxy.yml
- Add GALAXY_API_KEY to repo Actions secrets; verify manual dispatch and release trigger build + publish.

5) Sign-off Criteria
- [ ] Packaging exclusions validated against a fresh tarball
- [ ] Docs updated (changelog + harness references)
- [ ] Lint scope contained (flake8/ansible-lint config updated)
- [ ] Publish workflow merged and secret set (GALAXY_API_KEY)

Notes
- These steps keep internal test assets out of the public artifact, reduce CI noise, and maintain clear release documentation without changing customer-facing features.
