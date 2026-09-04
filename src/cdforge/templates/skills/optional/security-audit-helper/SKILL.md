---
name: security-audit-helper
description: Scan dependencies for known vulnerabilities and review new code for common security risks.
disable-model-invocation: true
---

Run `/security-audit-helper` to audit this project:

1. Run `uvx pip-audit` against the project's resolved dependencies and report any known
   vulnerabilities, with the affected package, installed version, and fixed version.
2. Review recently changed code for common risks: unsanitized input reaching a shell
   command, SQL, or template; secrets committed to the repository; missing authentication
   or authorization checks on new endpoints.
3. Prefer upgrading a vulnerable dependency to the fixed version over adding a workaround.
4. Report findings even when nothing is fixed yet - do not silently ignore a vulnerability
   that has no immediate fix available.
