# GitHub Settings Configuration

## Branch Protection Ruleset: trizel-main-protection

This directory contains the repository settings configuration file that defines branch protection rules for the main branch.

### Configuration File

**File**: `.github/settings.yml`

This YAML file defines the branch protection ruleset "trizel-main-protection" which was activated after PR #9 merge as part of the POST_MERGE_GOVERNANCE_LOCK procedure.

### Applying Settings

The `settings.yml` file can be applied using:

1. **GitHub Settings App/Probot** (recommended):
   - Install the [Settings](https://github.com/apps/settings) GitHub App
   - The app will automatically sync the settings from `settings.yml` to the repository

2. **Manual Configuration**:
   - Repository Settings → Branches → Add branch protection rule
   - Configure according to the specification in `settings.yml`

3. **GitHub API**:
   - Use the GitHub REST API to apply branch protection rules
   - Reference: https://docs.github.com/en/rest/branches/branch-protection

### Protection Rules Summary

For the `main` branch:
- ✅ Require pull request reviews (1 approving review)
- ✅ Require status checks to pass:
  - Pylint / build (3.8)
  - Pylint / build (3.9)
  - Pylint / build (3.10)
- ✅ Enforce for administrators
- ✅ Block force pushes
- ✅ Block branch deletion
- ✅ Require branches to be up to date before merging

### Verification

Current status and verification details are documented in:
- `docs/GOVERNANCE_LOCK_STATUS.md`

### Related Documentation

- `docs/GOVERNANCE_REFERENCE.md` - Overall governance framework
- `docs/GOVERNANCE_LOCK_STATUS.md` - Lock activation status and verification
