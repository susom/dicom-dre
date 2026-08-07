---
name: pr-template
description: 'Generate GitHub-flavored markdown for a pull request against the development branch, formatted as conventional-commit release notes for reuse as a squash/merge commit body. Use when writing a PR description, drafting release notes, or preparing a commit message body.'
argument-hint: 'against development; optional JIRA ticket'
---

# Pull Request Template

This skill generates a pull request description in GitHub-flavored markdown format
for the current branch against the development branch. The description is written as
conventional-commit release notes so it can be reused directly as the body of a
squash/merge commit that feeds python-semantic-release.

## When to Use

- Writing a pull request description for a branch targeting `development`
- Drafting release notes for a set of branch commits
- Preparing a squash/merge commit message body in conventional-commit format

## Output

The skill produces a markdown template containing:
- A conventional commit header line (`<type>[scope]: <description> (PROJ-12345)`)
- A short summary paragraph
- Change groups organized by conventional commit type (Features, Bug Fixes,
  Performance, Refactoring, Documentation, Tests), each as a bullet list
- An `### Interface and behavior changes` section when the branch changes existing
  behavior or removes a public interface

The output is formatted in a code block for easy copy/paste into GitHub and into a
commit message.

## Execution Steps

Large branches produce diff output that exceeds the terminal capture limit and gets
truncated. Gather change data with compact, aggregated commands first, then read
individual files or scoped diffs only when needed. Do not pipe these commands through
`head`/`tail`; that hides data rather than fixing truncation. Run each command
separately so one large result does not push another out of view.

### Step 1: Gather Branch Information

Get the current branch name:
```bash
git branch --show-current
```

Get commits not in development (short and complete; count first if it may be long):
```bash
git rev-list --count development..HEAD
git log --oneline development..HEAD
```

Get a per-directory change summary that stays small on large branches:
```bash
git diff development...HEAD --name-status | awk '{n=$1; $1=""; path=$0; sub(/^ /,"",path); d=path; sub(/\/[^\/]*$/,"",d); print n, d}' | sort | uniq -c | sort -rn
```

Get file-level status without the size graph (avoids per-line path truncation):
```bash
git diff development...HEAD --name-status
```

Use `--stat=200,200` only when line counts are needed; the wide format prevents path
and bar truncation:
```bash
git diff development...HEAD --stat=200,200
```

### Step 2: Analyze Changes

Work from the aggregated summaries in Step 1 to identify the change groups on the
branch. When a specific area needs detail, read the file directly or take a diff scoped
to one path rather than dumping the whole diff:
```bash
git diff development...HEAD -- <path>
```

Map each change to a conventional commit type:
- `feat` -> Features
- `fix` -> Bug Fixes
- `perf` -> Performance
- `refactor` -> Refactoring
- `docs` -> Documentation
- `test` -> Tests
- `chore` / `build` / `ci` -> Maintenance (only when relevant)

Summarize the branch by its net effect relative to `development`, not by its individual
commits. A `fix` commit only belongs under Bug Fixes when it corrects behavior that
already exists on `development` (a prior release). A commit that fixes code introduced
earlier in this same branch is part of building that feature, not a bug fix against a
release: fold it into the relevant Features bullet or omit it. To decide, check whether
the fixed code path exists on `development`:
```bash
git log --oneline development..HEAD -- <path>
```
If every commit touching that path is on this branch (nothing on `development`), treat
the change as feature development, not a Bug Fix.

Identify any change that alters existing behavior, removes a public interface, or
changes default output. List these under the interface and behavior changes section.
A change is only an interface or behavior change when it affects code that exists on
`development`; interfaces added and then adjusted within this branch are new, not changed.

### Step 3: Identify JIRA Ticket

Extract the JIRA ticket number from the branch name or commits (e.g., PROJ-12345).

### Step 4: Generate Release Notes

Write the description as conventional-commit release notes.

#### Header
Single conventional commit header line:
- `feat: add capability (PROJ-12345)`
- `fix: resolve issue (PROJ-12345)`
- `feat: replace legacy CLI with anonymize CLI (PROJ-12345)`
- `refactor: move result models (PROJ-12345)`

Use the type of the dominant change on the branch. If several types are present,
choose the highest-impact type (`feat` > `fix` > others).

#### Summary
One short paragraph (two to four sentences) describing what the branch does and why.
Keep it in present tense.

#### Change Groups
Add one `###` section per conventional commit type that applies, in this order:
Features, Bug Fixes, Performance, Refactoring, Documentation, Tests. Under each,
list changes as bullet points. Use a bold `**scope**:` lead-in where a scope
clarifies the entry. Omit any section that has no entries.

Before writing the Bug Fixes section, apply this gate to every candidate fix:
1. Identify the files the fix touches.
2. Run `git log --oneline development..HEAD -- <path>` and check whether the code being
   fixed already existed on `development`.
3. If the code path is net-new on this branch (all of its history is on the branch),
   the fix is part of building the feature. Do NOT list it under Bug Fixes; fold its
   substance into the matching Features bullet or drop it.
4. Only keep a bullet under Bug Fixes when it corrects behavior that shipped on
   `development` in a prior release.

On a feature branch this usually leaves Bug Fixes empty. That is expected; omit the
section entirely rather than repurposing it for intra-branch corrections.

#### Interface and behavior changes
When the branch changes existing behavior or removes a public interface, add a
`### Interface and behavior changes` section with one bullet per change. Do not add a
footer token.

#### De-identification rule and anonymizer changes
Do not compress de-identification rule or anonymizer edits into a single dense bullet. Give
each its own section and show the actual code so the reader can see exactly what changed.

- Changes to de-identification rules or profiles go under a
  `### De-identification rule changes` section. Show the affected rule text in a fenced code
  block, then describe each element's old -> new effect as bullets keyed by tag.
- Changes to the engine adapter or profile policy go under a `### Anonymizer changes`
  section. Show the relevant Python in a `python` fenced code block, then describe what
  each entry changes.

Gather the exact lines with scoped diffs, and render the resulting rule/catalog text in
the code block rather than the raw `+/-` diff:
```bash
git diff development...HEAD -- <path/to/rules>
git diff development...HEAD -- <path/to/engine> <path/to/profile>
```
Show only the elements that changed, one code block per rule family or catalog area,
with the prose description immediately beneath the block.

In each of these sections, also list the tests and regression-flow changes introduced
for the rule change, so the validation lives next to the rule it covers. Find them with
scoped diffs and name the specific test or flow behavior:
```bash
git diff development...HEAD --name-status -- tests
git diff development...HEAD -- <path/to/regression>
```
For example, note a new cross-reference test asserting a tag's action, a regression
comparison that now checks the tag, or a regression-flow change that exercises the rule.
When the same tests are already summarized under the Tests section, reference them here
rather than duplicating the full list.

### Step 5: Format Output

Wrap the entire template in a markdown code block so it copies cleanly into both the
GitHub PR field and a commit message:

````markdown
```markdown
feat: <short description> (PROJ-12345)

<one short summary paragraph>

### Features
- **scope**: change description
- change description

### Bug Fixes
- change description

### Documentation
- change description

### Tests
- change description

### Interface and behavior changes
- change description

### De-identification rule changes
```
<rule text that changed>
```
- (gggg,eeee) TagName: old -> new, and the effect on output
- Coverage: test or regression-flow change that validates this rule

### Anonymizer changes
```python
# profile / action code that changed
```
- description of what this entry changes
- Coverage: test or regression-flow change that validates this rule
```
````

## Tips

- Keep the summary paragraph short; put detail in the grouped bullet lists
- Use present tense ("adds feature" not "added feature")
- Group every change under the matching conventional commit type; omit empty groups
- Give de-identification rule changes and profile/catalog changes their own
  sections with the actual rule or catalog code in fenced code blocks and a per-item
  description; never compress them into one dense bullet, and list the tests or
  regression-flow changes that validate each rule alongside it
- Summarize net effect vs. `development`, not per-commit history. Fixes to code that was
  introduced earlier on this same branch are feature development, not Bug Fixes; fold
  them into the Features bullet or drop them. Reserve Bug Fixes for corrections to
  behavior that shipped in a prior release.
- Small commits with generic messages (e.g., "fix typo", "wip", "cleanup", "address
  review", "copilot feedback", "code review suggestions", formatting-only changes) can
  be excluded from the summary; roll them up or omit them rather than adding a bullet
  per commit
- Only include the `### Interface and behavior changes` section when the branch actually
  changes existing behavior or removes a public interface
- Follow conventional commits format for the header
- Extract JIRA ticket numbers from branch names (e.g., feat/PROJ-12345-description)

## Notes

- Always compare against the `development` branch, not `main`
- Use three-dot diff notation (`development...HEAD`) to see changes
- The output should be ready to paste directly into a GitHub PR description and reused
  as a squash/merge commit body
- The header type determines the version bump python-semantic-release applies
  (`feat` -> minor, `fix`/`perf` -> patch). Do not add a footer token.
- Markdown code blocks make it easy to copy/paste without formatting issues
