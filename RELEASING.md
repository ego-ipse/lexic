# Releasing Lexic

Releases are built from an exact tag on `main` and published to PyPI through
GitHub's OIDC trusted-publishing flow. No PyPI token is stored in GitHub.

## Repository setup

Complete this setup once after the release infrastructure has been merged into
`main`:

1. In the `ego-ipse/lexic` repository, create a GitHub environment named
   `pypi`. Add required reviewers if the publish should need manual approval.
2. In the verified PyPI account, open **Publishing** and add a pending trusted
   publisher with these exact values:

   - PyPI project name: `lexic`
   - GitHub owner: `ego-ipse`
   - GitHub repository: `lexic`
   - Workflow filename: `publish.yml`
   - Environment name: `pypi`

The pending publisher creates the PyPI project on the first successful run.
Configure it before pushing the tag; the workflow has no password fallback.

## Prepare a release

On a branch created from `main`:

1. Set `project.version` in `pyproject.toml` to the intended release version.
2. Run `uv lock` so the root package version in `uv.lock` matches.
3. Update release notes and any version-specific documentation.
4. Open a pull request and merge it into `main` after all checks pass.

## Publish from `main`

From an up-to-date, clean `main`, create a signed tag matching the merged
`project.version`. For the initial name-reservation release:

```bash
git tag -s v0.0.1 -m "Lexic 0.0.1"
git push origin v0.0.1
```

The workflow refuses a tag whose commit is not contained in `origin/main` or
whose name differs from `v` plus `project.version`. It runs repository checks,
examples, and tests; builds and checks the wheel and source distribution;
installs the wheel into a clean Python 3.14 environment; and only then gives
the separate publish job OIDC permission.

PyPI versions and filenames are immutable. If a run reaches PyPI and fails
after uploading either distribution, inspect the project before retrying; do
not reuse that version with changed contents.
