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

## Mandatory delivery verification
- A task is NOT complete merely because the files were edited or because a commit command was proposed.
- When a major change is completed, Cline MUST execute the Git operations itself when repository modification and push are authorized; do not merely provide the user with commands to run.
- After editing, run git status and verify that the intended files are actually modified.
- Before committing, run git diff (or an equivalent diff inspection) and verify that the commit contains only the intended changes.
- After git commit succeeds, immediately run git status --short --branch and git log -1 --oneline to verify that a real commit was created.
- Record and report the actual commit SHA and commit message. Never claim that changes are committed without seeing successful git commit output or independently verifying the resulting commit with git log.
- If the commit produces no changes or git reports that there is nothing to commit, do NOT claim the task was committed. Investigate why the expected changes are absent and report the actual state.
- After committing, run git push origin copilot/agents when push is authorized for the task.
- After pushing, independently verify the remote branch points to the new commit, using git ls-remote origin refs/heads/copilot/agents or an equivalent remote verification.
- Confirm that the remote SHA matches the newly created local commit SHA before claiming the task has been delivered.
- If push fails, is rejected, is blocked, or cannot be verified, do NOT claim the task is complete or pushed. Report the exact failure/state and leave the local commit intact for recovery.
- Never say "committed", "pushed", "available on GitHub", or equivalent unless the corresponding operation has actually succeeded and been verified.
- At the end of a successfully delivered major change, report: branch name, commit SHA, commit message, push result, and confirmation that local and remote commit SHAs match.
- If the user explicitly asks only for local changes and not a push, skip the push requirement but still verify the local commit and report its SHA.

## Validation
- Run the smallest relevant tests/checks after each major change before committing.
- If tests fail, fix the issue when it is within the scope of the current task; otherwise report the failure before committing.
