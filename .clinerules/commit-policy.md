# PitFUSION Cline project rules

## Repository and branch
- This workspace is the user's fork: https://github.com/AndrewRayR/PitFUSION
- Work only on the copilot/agents branch unless the user explicitly requests another branch.
- Keep origin pointed at https://github.com/AndrewRayR/PitFUSION.git.
- Do not switch to main or to the upstream repository unless explicitly instructed.

## Commit policy
- Treat a coherent feature, bug fix, refactor, configuration change, or other substantial unit of work as a major change.
- After completing and testing each major change, automatically create a Git commit on copilot/agents.
- Use a concise conventional commit message when appropriate.
- Before committing, inspect the diff and ensure no secrets, API keys, credentials, tokens, or machine-specific sensitive files are included.
- Do not make empty commits.
- Keep unrelated user changes out of the commit.
- After committing, verify the branch and commit status.
- Do not rewrite published history or force-push.
- Push completed major-change commits to origin/copilot/agents when the user has authorized the task to modify the remote repository.
- NEVER create, open, submit, or update a GitHub Pull Request as part of normal work.
- NEVER use a Pull Request as the mechanism for delivering changes to the user's repository.
- The normal delivery mechanism is: edit local files -> test -> git add -> git commit -> git push origin copilot/agents.
- Do not target another repository, upstream repository, or the default branch for changes unless the user explicitly requests it.

## Validation
- Run the smallest relevant tests/checks after each major change before committing.
- If tests fail, fix the issue when it is within the scope of the current task; otherwise report the failure before committing.

